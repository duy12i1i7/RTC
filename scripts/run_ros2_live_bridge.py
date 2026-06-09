"""Run a live rclpy-to-FleetRMW sidecar bridge.

This script requires a sourced ROS 2 environment.  It is intentionally thin:
all dependency-free config, buffering, and TCP logic lives in
``fleetqox.ros2_live_bridge``.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import math
import time
from typing import Mapping

from fleetqox.ros2_live_bridge import (
    BridgeTopicConfig,
    LiveBridgeConfig,
    Ros2LiveSampleBuffer,
    SidecarTcpClient,
    link_provider_for_config,
    load_bridge_config,
    transport_binding_provider_for_config,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="JSON bridge config with topics and sidecar endpoint")
    parser.add_argument("--sidecar-host", help="Override sidecar host from config")
    parser.add_argument("--sidecar-port", type=int, help="Override sidecar port from config")
    parser.add_argument("--max-batches", type=int, help="Stop after sending this many non-empty batches")
    parser.add_argument("--idle-timeout-s", type=float, help="Stop after this many idle seconds once at least one batch was sent")
    parser.add_argument("--max-runtime-s", type=float, help="Stop after this many seconds regardless of traffic")
    parser.add_argument("--stop-sidecar", action="store_true", help="Send a sidecar stop message on shutdown")
    args = parser.parse_args()

    config = load_bridge_config(args.config)
    if args.sidecar_host or args.sidecar_port is not None:
        config = replace(
            config,
            sidecar_host=args.sidecar_host or config.sidecar_host,
            sidecar_port=args.sidecar_port if args.sidecar_port is not None else config.sidecar_port,
        )
    run_live_bridge(
        config,
        max_batches=args.max_batches,
        idle_timeout_s=args.idle_timeout_s,
        max_runtime_s=args.max_runtime_s,
        stop_sidecar=args.stop_sidecar,
    )


def run_live_bridge(
    config: LiveBridgeConfig,
    *,
    max_batches: int | None = None,
    idle_timeout_s: float | None = None,
    max_runtime_s: float | None = None,
    stop_sidecar: bool = False,
) -> None:
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.serialization import serialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        raise SystemExit(
            "run_ros2_live_bridge requires a sourced ROS 2 Python environment with rclpy "
            "and rosidl_runtime_py available"
        ) from exc

    class FleetRmwLiveBridgeNode(Node):  # type: ignore[misc,valid-type]
        def __init__(self) -> None:
            super().__init__("fleetrmw_live_bridge")
            self.buffer = Ros2LiveSampleBuffer(
                scenario=config.scenario,
                link=config.link,
                include_feedback=config.include_feedback,
                link_provider=link_provider_for_config(config),
                transport_binding_provider=transport_binding_provider_for_config(config),
            )
            self.client = SidecarTcpClient(config.sidecar_host, config.sidecar_port)
            self.sent_batches = 0
            self.last_batch_monotonic = time.monotonic()
            self._stop_sidecar = stop_sidecar
            self.should_stop = False
            for topic_config in config.topics:
                self._subscribe(topic_config)
            self.create_timer(config.flush_period_ms / 1000.0, self._flush)
            self.get_logger().info(
                f"FleetRMW live bridge watching {len(config.topics)} topics; "
                f"sidecar={config.sidecar_host}:{config.sidecar_port}"
            )

        def _subscribe(self, topic_config: BridgeTopicConfig) -> None:
            message_type = get_message(topic_config.msg_type)
            qos_profile = _to_rclpy_qos(topic_config.qos)
            self.create_subscription(
                message_type,
                topic_config.topic,
                self._callback_for(topic_config),
                qos_profile,
            )
            self.get_logger().info(f"subscribed {topic_config.topic} as {topic_config.msg_type}")

        def _callback_for(self, topic_config: BridgeTopicConfig):
            def callback(message: object, message_info: object) -> None:
                try:
                    payload_size = len(serialize_message(message))
                except Exception:
                    payload_size = None
                source_metadata = _source_metadata_for_message_info(message_info)
                self.buffer.record_sample(
                    topic_config,
                    payload_size_bytes=payload_size,
                    publisher_gid=_optional_source_str(source_metadata.get("publisher_gid")),
                    sequence_number=_optional_source_int(source_metadata.get("sequence_number")),
                    source_timestamp_ns=_optional_source_int(source_metadata.get("source_timestamp_ns")),
                    received_timestamp_ns=_optional_source_int(source_metadata.get("received_timestamp_ns")),
                    semantic_payload=_semantic_payload_for_message(
                        topic_config,
                        message,
                        source_metadata=source_metadata,
                    ),
                )

            return callback

        def _flush(self) -> None:
            if self.buffer.pending_count() == 0:
                return
            batch = self.buffer.drain_batch()
            response = self.client.send_batch(batch)
            self.sent_batches += 1
            self.last_batch_monotonic = time.monotonic()
            emitted = response.get("emitted", 0)
            decisions = response.get("decisions", 0)
            self.get_logger().debug(
                f"sent batch tick={batch.get('tick')} decisions={decisions} emitted={emitted}"
            )
            if max_batches is not None and self.sent_batches >= max_batches:
                self.should_stop = True

        def destroy_node(self) -> bool:
            if self._stop_sidecar:
                try:
                    self.client.stop()
                except Exception as exc:
                    self.get_logger().warning(f"failed to stop sidecar cleanly: {exc}")
            self.client.close()
            return super().destroy_node()

    rclpy.init()
    node = FleetRmwLiveBridgeNode()
    started = time.monotonic()
    try:
        while rclpy.ok() and not node.should_stop:
            now = time.monotonic()
            if max_runtime_s is not None and now - started > max_runtime_s:
                break
            if idle_timeout_s is not None and node.sent_batches and now - node.last_batch_monotonic > idle_timeout_s:
                break
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def _to_rclpy_qos(ros2_qos):
    from rclpy.duration import Duration
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

    profile = QoSProfile(depth=max(1, ros2_qos.depth or 1))
    reliability = ros2_qos.reliability.lower()
    if "best" in reliability:
        profile.reliability = ReliabilityPolicy.BEST_EFFORT
    elif "reliable" in reliability:
        profile.reliability = ReliabilityPolicy.RELIABLE
    durability = ros2_qos.durability.lower()
    if "transient" in durability:
        profile.durability = DurabilityPolicy.TRANSIENT_LOCAL
    else:
        profile.durability = DurabilityPolicy.VOLATILE
    if ros2_qos.deadline_ms is not None:
        profile.deadline = _duration_from_ms(Duration, ros2_qos.deadline_ms)
    if ros2_qos.lifespan_ms is not None:
        profile.lifespan = _duration_from_ms(Duration, ros2_qos.lifespan_ms)
    if ros2_qos.liveliness_lease_ms is not None:
        profile.liveliness_lease_duration = _duration_from_ms(Duration, ros2_qos.liveliness_lease_ms)
    return profile


def _duration_from_ms(duration_cls, ms: float):
    nanoseconds = int(ms * 1_000_000)
    seconds = nanoseconds // 1_000_000_000
    remainder = nanoseconds % 1_000_000_000
    return duration_cls(seconds=seconds, nanoseconds=remainder)


def _semantic_payload_for_message(
    topic_config: BridgeTopicConfig,
    message: object,
    *,
    source_metadata: Mapping[str, object] | None = None,
) -> dict[str, object] | None:
    if topic_config.msg_type == "nav_msgs/msg/Odometry":
        return _with_source_metadata(_odometry_payload_for_message(topic_config, message), source_metadata)
    if topic_config.msg_type == "sensor_msgs/msg/LaserScan":
        return _with_source_metadata(_laser_scan_payload_for_message(topic_config, message), source_metadata)
    if topic_config.msg_type != "geometry_msgs/msg/Twist":
        return None
    linear = getattr(message, "linear", None)
    angular = getattr(message, "angular", None)
    if linear is None or angular is None:
        return None
    return _with_source_metadata(
        {
            "schema_version": "fleetrmw.semantic_payload.v1",
            "msg_type": topic_config.msg_type,
            "source_topic": topic_config.topic,
            "twist": {
                "linear": {
                    "x": _float_attr(linear, "x"),
                    "y": _float_attr(linear, "y"),
                    "z": _float_attr(linear, "z"),
                },
                "angular": {
                    "x": _float_attr(angular, "x"),
                    "y": _float_attr(angular, "y"),
                    "z": _float_attr(angular, "z"),
                },
            },
        },
        source_metadata,
    )


def _odometry_payload_for_message(topic_config: BridgeTopicConfig, message: object) -> dict[str, object] | None:
    pose = getattr(getattr(message, "pose", None), "pose", None)
    twist = getattr(getattr(message, "twist", None), "twist", None)
    if pose is None and twist is None:
        return None
    pose_covariance = getattr(getattr(message, "pose", None), "covariance", [])
    twist_covariance = getattr(getattr(message, "twist", None), "covariance", [])
    return {
        "schema_version": "fleetrmw.semantic_payload.v1",
        "msg_type": topic_config.msg_type,
        "source_topic": topic_config.topic,
        "header": _header_payload(getattr(message, "header", None)),
        "odometry": {
            "child_frame_id": str(getattr(message, "child_frame_id", "")),
            "pose": {
                "position": _vector_payload(getattr(pose, "position", None)),
                "orientation": _quaternion_payload(getattr(pose, "orientation", None)),
                "covariance": _float_sequence(pose_covariance, limit=36),
            },
            "twist": {
                "linear": _vector_payload(getattr(twist, "linear", None)),
                "angular": _vector_payload(getattr(twist, "angular", None)),
                "covariance": _float_sequence(twist_covariance, limit=36),
            },
        },
    }


def _laser_scan_payload_for_message(topic_config: BridgeTopicConfig, message: object) -> dict[str, object] | None:
    ranges = _float_sequence(getattr(message, "ranges", []))
    if not ranges:
        return None
    intensities = _float_sequence(getattr(message, "intensities", []))
    max_ranges = 60
    stride = max(1, math.ceil(len(ranges) / max_ranges))
    projected_ranges = ranges[::stride]
    projected_intensities = intensities[::stride] if intensities else []
    original_angle_increment = _float_attr(message, "angle_increment")
    angle_increment = original_angle_increment * stride
    angle_min = _float_attr(message, "angle_min")
    angle_max = angle_min + angle_increment * (len(projected_ranges) - 1) if projected_ranges else angle_min
    return {
        "schema_version": "fleetrmw.semantic_payload.v1",
        "msg_type": topic_config.msg_type,
        "source_topic": topic_config.topic,
        "header": _header_payload(getattr(message, "header", None)),
        "scan": {
            "angle_min": angle_min,
            "angle_max": angle_max,
            "angle_increment": angle_increment,
            "time_increment": _float_attr(message, "time_increment"),
            "scan_time": _float_attr(message, "scan_time"),
            "range_min": _float_attr(message, "range_min"),
            "range_max": _float_attr(message, "range_max"),
            "ranges": projected_ranges,
            "intensities": projected_intensities,
            "source_sample_count": len(ranges),
            "downsample_stride": stride,
        },
    }


def _source_metadata_for_message_info(message_info: object | None) -> dict[str, object]:
    if message_info is None:
        return {}
    metadata: dict[str, object] = {}
    publisher_gid = _publisher_gid_payload(_field_value(message_info, "publisher_gid"))
    if publisher_gid:
        metadata["publisher_gid"] = publisher_gid
    sequence_number = _int_attr_any(
        message_info,
        (
            "publication_sequence_number",
            "sequence_number",
            "source_sequence_number",
            "publisher_sequence_number",
        ),
    )
    if sequence_number is not None:
        metadata["sequence_number"] = sequence_number
    source_timestamp_ns = _int_attr_any(
        message_info,
        (
            "source_timestamp",
            "publication_timestamp",
            "source_timestamp_ns",
        ),
    )
    if source_timestamp_ns is not None:
        metadata["source_timestamp_ns"] = source_timestamp_ns
    received_timestamp_ns = _int_attr_any(
        message_info,
        (
            "received_timestamp",
            "reception_timestamp",
            "received_timestamp_ns",
        ),
    )
    if received_timestamp_ns is not None:
        metadata["received_timestamp_ns"] = received_timestamp_ns
    return metadata


def _with_source_metadata(
    payload: dict[str, object] | None,
    source_metadata: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if payload is None:
        return None
    clean = {
        str(key): value
        for key, value in dict(source_metadata or {}).items()
        if value is not None and value != ""
    }
    if not clean:
        return payload
    enriched = dict(payload)
    enriched["source_metadata"] = clean
    for key in ("publisher_gid", "sequence_number", "source_timestamp_ns", "received_timestamp_ns"):
        if key in clean:
            enriched[key] = clean[key]
    return enriched


def _publisher_gid_payload(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, Mapping):
        for key in ("data", "gid", "value", "bytes"):
            if key in value:
                return _publisher_gid_payload(value[key])
        return str(dict(value))
    if isinstance(value, bytes | bytearray):
        return bytes(value).hex()
    try:
        items = list(value)  # type: ignore[arg-type]
    except TypeError:
        return str(value)
    if not items:
        return None
    try:
        return "".join(f"{int(item) & 0xff:02x}" for item in items)
    except (TypeError, ValueError):
        return str(value)


def _int_attr_any(value: object, field_names: tuple[str, ...]) -> int | None:
    for field_name in field_names:
        parsed = _optional_source_int(_field_value(value, field_name))
        if parsed is not None:
            return parsed
    return None


def _field_value(value: object, field_name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _optional_source_str(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_source_int(value: object) -> int | None:
    try:
        return None if value is None or value == "" else int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _header_payload(header: object) -> dict[str, object]:
    stamp = getattr(header, "stamp", None)
    return {
        "frame_id": str(getattr(header, "frame_id", "")),
        "stamp": {
            "sec": _int_attr(stamp, "sec"),
            "nanosec": _int_attr(stamp, "nanosec"),
        },
    }


def _vector_payload(vector: object) -> dict[str, float]:
    return {
        "x": _float_attr(vector, "x"),
        "y": _float_attr(vector, "y"),
        "z": _float_attr(vector, "z"),
    }


def _quaternion_payload(quaternion: object) -> dict[str, float]:
    return {
        "x": _float_attr(quaternion, "x"),
        "y": _float_attr(quaternion, "y"),
        "z": _float_attr(quaternion, "z"),
        "w": _float_attr(quaternion, "w", default=1.0),
    }


def _float_sequence(value: object, *, limit: int | None = None) -> list[float]:
    try:
        items = list(value)  # type: ignore[arg-type]
    except TypeError:
        return []
    if limit is not None:
        items = items[:limit]
    return [_float_value(item) for item in items]


def _float_attr(value: object, field: str, *, default: float = 0.0) -> float:
    try:
        return float(getattr(value, field))
    except (AttributeError, TypeError, ValueError):
        return default


def _float_value(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _int_attr(value: object, field: str) -> int:
    try:
        return int(getattr(value, field))
    except (AttributeError, TypeError, ValueError):
        return 0


if __name__ == "__main__":
    main()
