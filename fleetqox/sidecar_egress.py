"""Sidecar UDP egress routing for ROS 2-facing control envelopes.

The runtime sidecar emits admitted packet events as JSON UDP datagrams.  This
module keeps the decoding and routing policy dependency-free so the behavior can
be unit-tested without ROS 2, while the executable bridge can publish the routed
envelopes through ``rclpy``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Mapping

from .projection_quality_ros import (
    FLEETRMW_QUALIFIED_LASER_SCAN_MSG_TYPE,
    FLEETRMW_QUALIFIED_ODOMETRY_MSG_TYPE,
)
from .rmw_contract import (
    QUALIFIED_PROJECTION_SCHEMA_VERSION,
    projected_sample_from_sidecar_event,
    projection_fidelity as contract_projection_fidelity,
    typed_projection_payload_base,
    valid_until_timestamp_ms,
)
from .rmw_frame import decode_data_frame, sidecar_event_from_data_frame
from .sidecar_contract import validate_event


STRING_MSG_TYPE = "std_msgs/msg/String"
_ROS_TOKEN_RE = re.compile(r"[^A-Za-z0-9_]")


@dataclass(frozen=True)
class EgressPublication:
    """A ROS-facing publication derived from one sidecar packet event."""

    topic: str
    msg_type: str
    payload: str
    kind: str
    event_id: int | None
    robot_id: str
    flow_id: str
    source_topic: str
    action: str
    wire_mode: str

    def as_log_record(self) -> dict[str, object]:
        return {
            "topic": self.topic,
            "msg_type": self.msg_type,
            "payload": self.payload,
            "kind": self.kind,
            "event_id": self.event_id,
            "robot_id": self.robot_id,
            "flow_id": self.flow_id,
            "source_topic": self.source_topic,
            "action": self.action,
            "wire_mode": self.wire_mode,
        }


@dataclass(frozen=True)
class SidecarEgressRouter:
    """Map sidecar wire modes to stable ROS 2 egress topics."""

    topic_prefix: str = "/fleetrmw"
    msg_type: str = STRING_MSG_TYPE
    enable_typed_reconstruction: bool = False
    include_projection_payload: bool = True
    projection_quality_msg_type: str = STRING_MSG_TYPE
    projection_quality_delivery: str = "sideband"

    def route(self, event: Mapping[str, object]) -> list[EgressPublication]:
        if str(event.get("event_type", "")) != "packet":
            return []

        robot_id = str(event.get("robot_id", "unknown_robot"))
        flow_id = str(event.get("flow_id", ""))
        source_topic = str(event.get("topic", ""))
        action = str(event.get("action", ""))
        wire_mode = str(event.get("wire_mode", "native"))
        kind, suffix = publication_kind_and_suffix(action=action, wire_mode=wire_mode)
        payload = payload_for_publication(kind=kind, event=event)

        publications = [
            EgressPublication(
                topic=f"{self._prefix()}/{ros_topic_token(robot_id)}/{suffix}",
                msg_type=self.msg_type,
                payload=payload,
                kind=kind,
                event_id=optional_int(event.get("event_id")),
                robot_id=robot_id,
                flow_id=flow_id,
                source_topic=source_topic,
                action=action,
                wire_mode=wire_mode,
            )
        ]
        if self.enable_typed_reconstruction:
            publications.extend(
                typed_publications_for_event(
                    event=event,
                    topic_prefix=self._prefix(),
                    include_projection_payload=self.include_projection_payload,
                    projection_quality_msg_type=self.projection_quality_msg_type,
                    projection_quality_delivery=self.projection_quality_delivery,
                )
            )
        return publications

    def _prefix(self) -> str:
        prefix = self.topic_prefix.strip() or "/fleetrmw"
        return "/" + prefix.strip("/")


def decode_sidecar_packet(data: bytes, *, validate: bool = True) -> dict[str, object] | None:
    """Decode a padded sidecar UDP packet.

    The decoder accepts both the original padded JSON sidecar event and the new
    magic-prefixed ``fleetrmw.data_frame.v1`` format.  Frame bytes are converted
    back to the event view used by the current egress router.
    """

    frame = decode_data_frame(data)
    if frame is not None:
        event = sidecar_event_from_data_frame(frame)
    else:
        try:
            payload = json.loads(data.rstrip(b" ").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        event = dict(payload)
    if validate:
        try:
            validate_event(event)
        except ValueError:
            return None
    return event


def publication_kind_and_suffix(*, action: str, wire_mode: str) -> tuple[str, str]:
    if action == "send_supervisory_intent" or wire_mode == "supervisory_intent":
        return "supervisory_intent", "control_lease"
    if action == "send_intent" or wire_mode == "control_intent":
        return "control_intent", "control_lease"
    if action == "send_degraded" or wire_mode == "degraded":
        return "degraded", "degraded"
    if action == "send_compacted" or wire_mode == "semantic_delta":
        return "semantic_delta", "semantic_delta"
    return "native", "native_trace"


def payload_for_publication(*, kind: str, event: Mapping[str, object]) -> str:
    timestamp_ms = optional_float(event.get("timestamp_ms"))
    lifespan_ms = optional_float(event.get("lifespan_ms"))
    valid_until_ms = None
    if timestamp_ms is not None and lifespan_ms is not None:
        valid_until_ms = timestamp_ms + lifespan_ms

    payload = {
        "schema_version": "fleetrmw.egress.envelope.v1",
        "kind": kind,
        "event_id": optional_int(event.get("event_id")),
        "scenario": optional_str(event.get("scenario")),
        "policy": optional_str(event.get("policy")),
        "timestamp_ms": timestamp_ms,
        "valid_until_timestamp_ms": valid_until_ms,
        "robot_id": optional_str(event.get("robot_id")),
        "flow_id": optional_str(event.get("flow_id")),
        "flow_class": optional_str(event.get("flow_class")),
        "source_topic": optional_str(event.get("topic")),
        "action": optional_str(event.get("action")),
        "wire_mode": optional_str(event.get("wire_mode")),
        "reason": optional_str(event.get("reason")),
        "bytes": optional_int(event.get("bytes")),
        "original_bytes": optional_int(event.get("original_bytes")),
        "deadline_ms": optional_float(event.get("deadline_ms")),
        "source_deadline_ms": optional_float(event.get("source_deadline_ms")),
        "lifespan_ms": lifespan_ms,
        "reliability": optional_str(event.get("reliability")),
        "qos_reliability": optional_str(event.get("qos_reliability")),
        "predicted_slack_ms": optional_float(event.get("predicted_slack_ms")),
        "semantic_utility": optional_float(event.get("semantic_utility")),
        "age_ms": optional_float(event.get("age_ms")),
        "queue_depth": optional_int(event.get("queue_depth")),
        "task": {
            "criticality": optional_float(event.get("task_criticality")),
            "collision_risk": optional_float(event.get("collision_risk")),
            "operator_attention": optional_float(event.get("operator_attention")),
            "coordination_pressure": optional_float(event.get("coordination_pressure")),
        },
        "link": {
            "capacity_bytes_per_tick": optional_int(event.get("link_capacity_bytes_per_tick")),
            "loss": optional_float(event.get("link_loss")),
            "jitter_ms": optional_float(event.get("link_jitter_ms")),
            "rtt_ms": optional_float(event.get("link_rtt_ms")),
        },
    }
    semantic_payload = event.get("semantic_payload")
    if isinstance(semantic_payload, Mapping):
        payload["semantic_payload"] = dict(semantic_payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def robot_feedback_record_from_event(
    event: Mapping[str, object],
    *,
    recv_monotonic_ns: int,
) -> dict[str, object] | None:
    """Build receiver-side feedback for the budget-aware sidecar controller."""

    robot_id = optional_str(event.get("robot_id"))
    if not robot_id:
        return None
    flow_class = optional_str(event.get("flow_class")) or ""
    record: dict[str, object] = {
        "schema_version": "fleetrmw.robot_feedback.v1",
        "source": "egress",
        "robot_id": robot_id,
        "flow_id": optional_str(event.get("flow_id")) or "",
        "flow_class": flow_class,
        "source_topic": optional_str(event.get("topic")) or "",
        "action": optional_str(event.get("action")) or "",
        "wire_mode": optional_str(event.get("wire_mode")) or "",
        "event_id": optional_int(event.get("event_id")),
        "received": True,
    }
    add_source_identity_to_feedback_record(record, event)
    if flow_class == "control":
        record["control_delivered"] = True

    send_ns = optional_int(event.get("send_monotonic_ns"))
    deadline_ms = optional_float(event.get("deadline_ms"))
    age_ms = optional_float(event.get("age_ms")) or 0.0
    if send_ns is not None and deadline_ms is not None:
        latency_ms = max(0.0, (recv_monotonic_ns - send_ns) / 1_000_000.0)
        arrival_age_ms = age_ms + latency_ms
        deadline_met = arrival_age_ms <= deadline_ms
        record["latency_ms"] = latency_ms
        record["arrival_age_ms"] = arrival_age_ms
        record["deadline_ms"] = deadline_ms
        record["deadline_met"] = deadline_met
        record["deadline_risk"] = 0.0 if deadline_met else 1.0
    return record


def add_source_identity_to_feedback_record(
    record: dict[str, object],
    event: Mapping[str, object],
) -> None:
    semantic_payload = event.get("semantic_payload")
    semantic_payload = semantic_payload if isinstance(semantic_payload, Mapping) else {}
    source_sample_id = optional_str(event.get("source_sample_id")) or optional_str(
        semantic_payload.get("source_sample_id")
    )
    if source_sample_id:
        record["source_sample_id"] = source_sample_id
    source_metadata = event.get("source_metadata")
    if not isinstance(source_metadata, Mapping):
        source_metadata = semantic_payload.get("source_metadata")
    if not isinstance(source_metadata, Mapping):
        return
    sequence_number = optional_int(source_metadata.get("sequence_number"))
    if sequence_number is not None:
        record["source_sequence_number"] = sequence_number
    source_timestamp_ns = optional_int(source_metadata.get("source_timestamp_ns"))
    if source_timestamp_ns is not None:
        record["source_timestamp_ns"] = source_timestamp_ns
    received_timestamp_ns = optional_int(source_metadata.get("received_timestamp_ns"))
    if received_timestamp_ns is not None:
        record["source_received_timestamp_ns"] = received_timestamp_ns


def typed_publications_for_event(
    *,
    event: Mapping[str, object],
    topic_prefix: str,
    include_projection_payload: bool = True,
    projection_quality_msg_type: str = STRING_MSG_TYPE,
    projection_quality_delivery: str = "sideband",
) -> list[EgressPublication]:
    semantic_payload = event.get("semantic_payload")
    if not isinstance(semantic_payload, Mapping):
        return []
    msg_type = str(semantic_payload.get("msg_type", ""))
    if msg_type == "geometry_msgs/msg/Twist":
        return typed_twist_publications_for_event(
            event=event,
            semantic_payload=semantic_payload,
            topic_prefix=topic_prefix,
            include_projection_payload=include_projection_payload,
            projection_quality_msg_type=projection_quality_msg_type,
            projection_quality_delivery=projection_quality_delivery,
        )
    if msg_type == "nav_msgs/msg/Odometry":
        return typed_odom_publications_for_event(
            event=event,
            semantic_payload=semantic_payload,
            topic_prefix=topic_prefix,
            include_projection_payload=include_projection_payload,
            projection_quality_msg_type=projection_quality_msg_type,
            projection_quality_delivery=projection_quality_delivery,
        )
    if msg_type == "sensor_msgs/msg/LaserScan":
        return typed_scan_publications_for_event(
            event=event,
            semantic_payload=semantic_payload,
            topic_prefix=topic_prefix,
            include_projection_payload=include_projection_payload,
            projection_quality_msg_type=projection_quality_msg_type,
            projection_quality_delivery=projection_quality_delivery,
        )
    return []


def typed_twist_publications_for_event(
    *,
    event: Mapping[str, object],
    semantic_payload: Mapping[str, object],
    topic_prefix: str,
    include_projection_payload: bool = True,
    projection_quality_msg_type: str = STRING_MSG_TYPE,
    projection_quality_delivery: str = "sideband",
) -> list[EgressPublication]:
    twist = semantic_payload.get("twist")
    if not isinstance(twist, Mapping):
        return []

    robot_id = str(event.get("robot_id", "unknown_robot"))
    topic = f"{topic_prefix}/{ros_topic_token(robot_id)}/local_cmd_vel"
    payload = json.dumps(
        _typed_payload_base(event, kind="typed_twist", projection_topic=topic)
        | {
            "twist": sanitize_twist_payload(twist),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    publications = [
        EgressPublication(
            topic=topic,
            msg_type="geometry_msgs/msg/Twist",
            payload=payload,
            kind="typed_twist",
            event_id=optional_int(event.get("event_id")),
            robot_id=robot_id,
            flow_id=str(event.get("flow_id", "")),
            source_topic=str(event.get("topic", "")),
            action=str(event.get("action", "")),
            wire_mode=str(event.get("wire_mode", "native")),
        )
    ]
    if projection_quality_delivery in {"sideband", "both"}:
        publications.append(
            projection_quality_publication(
                event=event,
                semantic_payload=semantic_payload,
                topic_prefix=topic_prefix,
                projection_kind="typed_twist",
                projection_topic=topic,
                projection_msg_type="geometry_msgs/msg/Twist",
                projection_payload=json.loads(payload),
                include_projection_payload=include_projection_payload,
                projection_quality_msg_type=projection_quality_msg_type,
            )
        )
    return publications


def typed_odom_publications_for_event(
    *,
    event: Mapping[str, object],
    semantic_payload: Mapping[str, object],
    topic_prefix: str,
    include_projection_payload: bool = True,
    projection_quality_msg_type: str = STRING_MSG_TYPE,
    projection_quality_delivery: str = "sideband",
) -> list[EgressPublication]:
    odometry = semantic_payload.get("odometry")
    if not isinstance(odometry, Mapping):
        return []

    robot_id = str(event.get("robot_id", "unknown_robot"))
    topic = f"{topic_prefix}/{ros_topic_token(robot_id)}/local_odom"
    payload = json.dumps(
        _typed_payload_base(event, kind="typed_odom", projection_topic=topic)
        | {
            "header": sanitize_header_payload(semantic_payload.get("header")),
            "odometry": sanitize_odometry_payload(odometry),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    typed_publication = EgressPublication(
        topic=topic,
        msg_type="nav_msgs/msg/Odometry",
        payload=payload,
        kind="typed_odom",
        event_id=optional_int(event.get("event_id")),
        robot_id=robot_id,
        flow_id=str(event.get("flow_id", "")),
        source_topic=str(event.get("topic", "")),
        action=str(event.get("action", "")),
        wire_mode=str(event.get("wire_mode", "native")),
    )
    publications = []
    typed_payload = json.loads(payload)
    quality_payload = projection_quality_payload(
        event=event,
        semantic_payload=semantic_payload,
        projection_kind="typed_odom",
        projection_topic=topic,
        projection_msg_type="nav_msgs/msg/Odometry",
        projection_payload=typed_payload,
        include_projection_payload=include_projection_payload,
    )
    if projection_quality_delivery in {"sideband", "both"}:
        publications.append(typed_publication)
        publications.append(
            projection_quality_publication(
                event=event,
                semantic_payload=semantic_payload,
                topic_prefix=topic_prefix,
                projection_kind="typed_odom",
                projection_topic=topic,
                projection_msg_type="nav_msgs/msg/Odometry",
                projection_payload=typed_payload,
                include_projection_payload=include_projection_payload,
                projection_quality_msg_type=projection_quality_msg_type,
            )
        )
    if projection_quality_delivery in {"wrapper", "both"}:
        publications.append(
            qualified_projection_publication(
                event=event,
                topic_prefix=topic_prefix,
                suffix="qualified_odom",
                msg_type=FLEETRMW_QUALIFIED_ODOMETRY_MSG_TYPE,
                kind="qualified_odom",
                sample_payload=typed_payload,
                quality_payload=quality_payload,
            )
        )
    return publications


def typed_scan_publications_for_event(
    *,
    event: Mapping[str, object],
    semantic_payload: Mapping[str, object],
    topic_prefix: str,
    include_projection_payload: bool = True,
    projection_quality_msg_type: str = STRING_MSG_TYPE,
    projection_quality_delivery: str = "sideband",
) -> list[EgressPublication]:
    scan = semantic_payload.get("scan")
    if not isinstance(scan, Mapping):
        return []

    robot_id = str(event.get("robot_id", "unknown_robot"))
    topic = f"{topic_prefix}/{ros_topic_token(robot_id)}/local_scan"
    payload = json.dumps(
        _typed_payload_base(event, kind="typed_scan", projection_topic=topic)
        | {
            "header": sanitize_header_payload(semantic_payload.get("header")),
            "scan": sanitize_laser_scan_payload(scan),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    typed_publication = EgressPublication(
        topic=topic,
        msg_type="sensor_msgs/msg/LaserScan",
        payload=payload,
        kind="typed_scan",
        event_id=optional_int(event.get("event_id")),
        robot_id=robot_id,
        flow_id=str(event.get("flow_id", "")),
        source_topic=str(event.get("topic", "")),
        action=str(event.get("action", "")),
        wire_mode=str(event.get("wire_mode", "native")),
    )
    publications = []
    typed_payload = json.loads(payload)
    quality_payload = projection_quality_payload(
        event=event,
        semantic_payload=semantic_payload,
        projection_kind="typed_scan",
        projection_topic=topic,
        projection_msg_type="sensor_msgs/msg/LaserScan",
        projection_payload=typed_payload,
        include_projection_payload=include_projection_payload,
    )
    if projection_quality_delivery in {"sideband", "both"}:
        publications.append(typed_publication)
        publications.append(
            projection_quality_publication(
                event=event,
                semantic_payload=semantic_payload,
                topic_prefix=topic_prefix,
                projection_kind="typed_scan",
                projection_topic=topic,
                projection_msg_type="sensor_msgs/msg/LaserScan",
                projection_payload=typed_payload,
                include_projection_payload=include_projection_payload,
                projection_quality_msg_type=projection_quality_msg_type,
            )
        )
    if projection_quality_delivery in {"wrapper", "both"}:
        publications.append(
            qualified_projection_publication(
                event=event,
                topic_prefix=topic_prefix,
                suffix="qualified_scan",
                msg_type=FLEETRMW_QUALIFIED_LASER_SCAN_MSG_TYPE,
                kind="qualified_scan",
                sample_payload=typed_payload,
                quality_payload=quality_payload,
            )
        )
    return publications


def qualified_projection_publication(
    *,
    event: Mapping[str, object],
    topic_prefix: str,
    suffix: str,
    msg_type: str,
    kind: str,
    sample_payload: Mapping[str, object],
    quality_payload: Mapping[str, object],
) -> EgressPublication:
    robot_id = str(event.get("robot_id", "unknown_robot"))
    payload = json.dumps(
        {
            "schema_version": QUALIFIED_PROJECTION_SCHEMA_VERSION,
            "kind": kind,
            "sample": dict(sample_payload),
            "quality": dict(quality_payload),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return EgressPublication(
        topic=f"{topic_prefix}/{ros_topic_token(robot_id)}/{suffix}",
        msg_type=msg_type,
        payload=payload,
        kind=kind,
        event_id=optional_int(event.get("event_id")),
        robot_id=robot_id,
        flow_id=str(event.get("flow_id", "")),
        source_topic=str(event.get("topic", "")),
        action=str(event.get("action", "")),
        wire_mode=str(event.get("wire_mode", "native")),
    )


def projection_quality_publication(
    *,
    event: Mapping[str, object],
    semantic_payload: Mapping[str, object],
    topic_prefix: str,
    projection_kind: str,
    projection_topic: str,
    projection_msg_type: str,
    projection_payload: Mapping[str, object],
    include_projection_payload: bool = True,
    projection_quality_msg_type: str = STRING_MSG_TYPE,
) -> EgressPublication:
    robot_id = str(event.get("robot_id", "unknown_robot"))
    payload = json.dumps(
        projection_quality_payload(
            event=event,
            semantic_payload=semantic_payload,
            projection_kind=projection_kind,
            projection_topic=projection_topic,
            projection_msg_type=projection_msg_type,
            projection_payload=projection_payload,
            include_projection_payload=include_projection_payload,
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    return EgressPublication(
        topic=f"{topic_prefix}/{ros_topic_token(robot_id)}/projection_quality",
        msg_type=projection_quality_msg_type,
        payload=payload,
        kind="typed_projection_quality",
        event_id=optional_int(event.get("event_id")),
        robot_id=robot_id,
        flow_id=str(event.get("flow_id", "")),
        source_topic=str(event.get("topic", "")),
        action=str(event.get("action", "")),
        wire_mode=str(event.get("wire_mode", "native")),
    )


def projection_quality_payload(
    *,
    event: Mapping[str, object],
    semantic_payload: Mapping[str, object],
    projection_kind: str,
    projection_topic: str,
    projection_msg_type: str,
    projection_payload: Mapping[str, object],
    include_projection_payload: bool = True,
) -> dict[str, object]:
    return projected_sample_from_sidecar_event(
        event=event,
        semantic_payload=semantic_payload,
        projection_kind=projection_kind,
        projection_topic=projection_topic,
        projection_msg_type=projection_msg_type,
        projection_payload=projection_payload,
        include_projection_payload=include_projection_payload,
    ).quality_payload()


def projection_fidelity(
    *,
    event: Mapping[str, object],
    projection_kind: str,
    projection_payload: Mapping[str, object],
) -> dict[str, object]:
    return contract_projection_fidelity(
        event=event,
        projection_kind=projection_kind,
        projection_payload=projection_payload,
    )


def _typed_payload_base(
    event: Mapping[str, object],
    *,
    kind: str,
    projection_topic: str,
) -> dict[str, object]:
    return typed_projection_payload_base(event, kind=kind, projection_topic=projection_topic)


def sanitize_twist_payload(twist: Mapping[str, object]) -> dict[str, dict[str, float]]:
    linear = twist.get("linear")
    angular = twist.get("angular")
    linear_map = linear if isinstance(linear, Mapping) else {}
    angular_map = angular if isinstance(angular, Mapping) else {}
    return {
        "linear": {
            "x": optional_float(linear_map.get("x")) or 0.0,
            "y": optional_float(linear_map.get("y")) or 0.0,
            "z": optional_float(linear_map.get("z")) or 0.0,
        },
        "angular": {
            "x": optional_float(angular_map.get("x")) or 0.0,
            "y": optional_float(angular_map.get("y")) or 0.0,
            "z": optional_float(angular_map.get("z")) or 0.0,
        },
    }


def sanitize_header_payload(header: object) -> dict[str, object]:
    data = header if isinstance(header, Mapping) else {}
    stamp = data.get("stamp")
    stamp_map = stamp if isinstance(stamp, Mapping) else {}
    return {
        "frame_id": optional_str(data.get("frame_id")) or "",
        "stamp": {
            "sec": optional_int(stamp_map.get("sec")) or 0,
            "nanosec": optional_int(stamp_map.get("nanosec")) or 0,
        },
    }


def sanitize_odometry_payload(odometry: Mapping[str, object]) -> dict[str, object]:
    pose = odometry.get("pose")
    twist = odometry.get("twist")
    pose_map = pose if isinstance(pose, Mapping) else {}
    twist_map = twist if isinstance(twist, Mapping) else {}
    return {
        "child_frame_id": optional_str(odometry.get("child_frame_id")) or "",
        "pose": {
            "position": sanitize_vector_payload(pose_map.get("position")),
            "orientation": sanitize_quaternion_payload(pose_map.get("orientation")),
            "covariance": sanitize_float_list(pose_map.get("covariance"), limit=36),
        },
        "twist": {
            "linear": sanitize_vector_payload(twist_map.get("linear")),
            "angular": sanitize_vector_payload(twist_map.get("angular")),
            "covariance": sanitize_float_list(twist_map.get("covariance"), limit=36),
        },
    }


def sanitize_laser_scan_payload(scan: Mapping[str, object]) -> dict[str, object]:
    return {
        "angle_min": optional_float(scan.get("angle_min")) or 0.0,
        "angle_max": optional_float(scan.get("angle_max")) or 0.0,
        "angle_increment": optional_float(scan.get("angle_increment")) or 0.0,
        "time_increment": optional_float(scan.get("time_increment")) or 0.0,
        "scan_time": optional_float(scan.get("scan_time")) or 0.0,
        "range_min": optional_float(scan.get("range_min")) or 0.0,
        "range_max": optional_float(scan.get("range_max")) or 0.0,
        "ranges": sanitize_float_list(scan.get("ranges")),
        "intensities": sanitize_float_list(scan.get("intensities")),
        "source_sample_count": optional_int(scan.get("source_sample_count")) or 0,
        "downsample_stride": optional_int(scan.get("downsample_stride")) or 1,
    }


def sanitize_vector_payload(vector: object) -> dict[str, float]:
    data = vector if isinstance(vector, Mapping) else {}
    return {
        "x": optional_float(data.get("x")) or 0.0,
        "y": optional_float(data.get("y")) or 0.0,
        "z": optional_float(data.get("z")) or 0.0,
    }


def sanitize_quaternion_payload(quaternion: object) -> dict[str, float]:
    data = quaternion if isinstance(quaternion, Mapping) else {}
    return {
        "x": optional_float(data.get("x")) or 0.0,
        "y": optional_float(data.get("y")) or 0.0,
        "z": optional_float(data.get("z")) or 0.0,
        "w": optional_float(data.get("w")) or 1.0,
    }


def sanitize_float_list(value: object, *, limit: int | None = None) -> list[float]:
    if not isinstance(value, list | tuple):
        return []
    items = list(value[:limit] if limit is not None else value)
    return [optional_float(item) or 0.0 for item in items]


def _valid_until_timestamp_ms(event: Mapping[str, object]) -> float | None:
    return valid_until_timestamp_ms(event)


def ros_topic_token(value: str) -> str:
    token = _ROS_TOKEN_RE.sub("_", value.strip())
    token = token.strip("_")
    if not token:
        return "unknown"
    if token[0].isdigit():
        return f"r_{token}"
    return token


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def optional_int(value: object) -> int | None:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def optional_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
