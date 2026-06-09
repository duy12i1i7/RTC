"""Gate FleetRMW typed projections using projection-quality identity metadata."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import json
import time
from pathlib import Path
from typing import Mapping

from fleetqox.projection_identity import projection_signature
from fleetqox.projection_quality_ros import projection_quality_payload_from_message
from fleetqox.projection_quality_gate import (
    PROJECTION_QUALITY_GATE_SCHEMA_VERSION,
    ProjectionGatePolicy,
    ProjectionQuality,
    ProjectionQualityGate,
)
from fleetqox.sidecar_runtime import RobotFeedbackTcpClient, send_robot_feedback


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robot-id", default="robot_0000")
    parser.add_argument("--robot-count", type=int, default=1)
    parser.add_argument("--quality-topic")
    parser.add_argument("--odom-topic")
    parser.add_argument("--scan-topic")
    parser.add_argument("--qualified-odom-topic")
    parser.add_argument("--qualified-scan-topic")
    parser.add_argument("--accepted-odom-topic")
    parser.add_argument("--accepted-scan-topic")
    parser.add_argument("--decision-log", type=Path, default=Path("results_ros2_live_bridge/projection_quality_gate.jsonl"))
    parser.add_argument("--identity-mode", choices=("signature", "payload", "wrapper"), default="wrapper")
    parser.add_argument("--quality-message-mode", choices=("typed", "string"), default="typed")
    parser.add_argument("--max-projection-age-ms", type=float, default=350.0)
    parser.add_argument("--max-downsample-stride", type=int, default=3)
    parser.add_argument("--min-projected-scan-ranges", type=int, default=30)
    parser.add_argument("--reject-downsampled-collision-risk-at", type=float, default=0.65)
    parser.add_argument("--max-pending-per-signature", type=int, default=8)
    parser.add_argument("--allow-degraded", action="store_true")
    parser.add_argument("--idle-timeout-s", type=float, default=4.0)
    parser.add_argument("--max-runtime-s", type=float, default=120.0)
    parser.add_argument("--feedback-sidecar-host")
    parser.add_argument("--feedback-sidecar-port", type=int, default=8765)
    parser.add_argument("--feedback-timeout-s", type=float, default=0.25)
    parser.add_argument("--feedback-every-decisions", type=int, default=12)
    args = parser.parse_args()

    try:
        import rclpy
        from nav_msgs.msg import Odometry
        from sensor_msgs.msg import LaserScan
        from std_msgs.msg import String
        ProjectionQualityMsg = None
        QualifiedOdometry = None
        QualifiedLaserScan = None
        if args.quality_message_mode == "typed":
            from fleetrmw_interfaces.msg import (
                ProjectionQuality as ProjectionQualityMsg,
                QualifiedLaserScan,
                QualifiedOdometry,
            )
    except ImportError as exc:
        raise SystemExit("ROS 2 rclpy, nav_msgs, sensor_msgs, std_msgs, and fleetrmw_interfaces are required for projection quality gate") from exc

    robot_ids = robot_ids_for_args(args.robot_id, args.robot_count)
    policy = ProjectionGatePolicy(
        allow_degraded_projection=args.allow_degraded,
        max_projection_age_ms=args.max_projection_age_ms,
        max_downsample_stride=args.max_downsample_stride,
        min_projected_scan_ranges=args.min_projected_scan_ranges,
        reject_downsampled_collision_risk_at=args.reject_downsampled_collision_risk_at,
    )
    args.decision_log.parent.mkdir(parents=True, exist_ok=True)

    rclpy.init()
    node = rclpy.create_node("fleetrmw_projection_quality_gate")
    started = time.monotonic()
    last_activity = started
    counters: Counter[str] = Counter()
    counters_by_robot: dict[str, Counter[str]] = {
        robot_id: Counter() for robot_id in robot_ids
    }
    feedback_window: list[dict[str, object]] = []
    feedback_client = (
        RobotFeedbackTcpClient(
            host=args.feedback_sidecar_host,
            port=args.feedback_sidecar_port,
            timeout_s=args.feedback_timeout_s,
        )
        if args.feedback_sidecar_host
        else None
    )
    contexts = []
    for robot_id in robot_ids:
        quality_topic = topic_for_robot(
            args.quality_topic,
            default_template="/fleetrmw/{robot_id}/projection_quality",
            base_robot_id=args.robot_id,
            robot_id=robot_id,
        )
        odom_topic = topic_for_robot(
            args.odom_topic,
            default_template="/fleetrmw/{robot_id}/local_odom",
            base_robot_id=args.robot_id,
            robot_id=robot_id,
        )
        scan_topic = topic_for_robot(
            args.scan_topic,
            default_template="/fleetrmw/{robot_id}/local_scan",
            base_robot_id=args.robot_id,
            robot_id=robot_id,
        )
        qualified_odom_topic = topic_for_robot(
            args.qualified_odom_topic,
            default_template="/fleetrmw/{robot_id}/qualified_odom",
            base_robot_id=args.robot_id,
            robot_id=robot_id,
        )
        qualified_scan_topic = topic_for_robot(
            args.qualified_scan_topic,
            default_template="/fleetrmw/{robot_id}/qualified_scan",
            base_robot_id=args.robot_id,
            robot_id=robot_id,
        )
        accepted_odom_topic = topic_for_robot(
            args.accepted_odom_topic,
            default_template="/fleetrmw/{robot_id}/accepted_odom",
            base_robot_id=args.robot_id,
            robot_id=robot_id,
        )
        accepted_scan_topic = topic_for_robot(
            args.accepted_scan_topic,
            default_template="/fleetrmw/{robot_id}/accepted_scan",
            base_robot_id=args.robot_id,
            robot_id=robot_id,
        )
        odom_pub = node.create_publisher(Odometry, accepted_odom_topic, 10)
        scan_pub = node.create_publisher(LaserScan, accepted_scan_topic, 10)
        contexts.append(
            {
                "robot_id": robot_id,
                "gate": ProjectionQualityGate(policy),
                "quality_topic": quality_topic,
                "odom_topic": odom_topic,
                "scan_topic": scan_topic,
                "qualified_odom_topic": qualified_odom_topic,
                "qualified_scan_topic": qualified_scan_topic,
                "accepted_odom_topic": accepted_odom_topic,
                "accepted_scan_topic": accepted_scan_topic,
                "pending_quality": defaultdict(deque),
                "pending_messages": defaultdict(deque),
                "target_by_kind": {
                    "typed_odom": {
                        "publisher": odom_pub,
                        "projection_topic": odom_topic,
                        "accepted_topic": accepted_odom_topic,
                        "payload_factory": lambda payload: odometry_from_projection_payload(Odometry, payload),
                    },
                    "typed_scan": {
                        "publisher": scan_pub,
                        "projection_topic": scan_topic,
                        "accepted_topic": accepted_scan_topic,
                        "payload_factory": lambda payload: laser_scan_from_projection_payload(LaserScan, payload),
                    },
                },
            }
        )

    with args.decision_log.open("w", encoding="utf-8") as handle:

        def bump(robot_id: str, key: str) -> None:
            counters[key] += 1
            counters_by_robot[robot_id][key] += 1

        def write_record(record: dict[str, object]) -> None:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            feedback_record = quality_gate_feedback_record(record)
            if feedback_record is not None:
                feedback_window.append(feedback_record)
                sent, failed = flush_feedback_window(
                    args,
                    feedback_window,
                    feedback_client=feedback_client,
                )
                counters["feedback_sent"] += sent
                counters["feedback_failed"] += failed

        def quality_callback_for(ctx: Mapping[str, object]):
            def _callback(message: object) -> None:
                nonlocal last_activity
                robot_id = str(ctx["robot_id"])
                last_activity = time.monotonic()
                bump(robot_id, "quality")
                try:
                    quality = quality_from_ros_message(message)
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    bump(robot_id, "invalid_quality")
                    write_record(
                        {
                            "schema_version": PROJECTION_QUALITY_GATE_SCHEMA_VERSION,
                            "event_type": "quality_projection",
                            "robot_id": robot_id,
                            "projection_identity_mode": args.identity_mode,
                            "quality_message_mode": args.quality_message_mode,
                            "status": "invalid_quality",
                            "reason": str(exc),
                            "publish": False,
                        }
                    )
                    return

                decision = ctx["gate"].evaluate(quality)  # type: ignore[union-attr]
                record = decision.as_log_record()
                record["event_type"] = "quality_projection"
                record["robot_id"] = record.get("robot_id") or robot_id
                record["accepted_topic"] = None
                record["projection_identity_mode"] = args.identity_mode
                record["quality_message_mode"] = args.quality_message_mode
                target = ctx["target_by_kind"].get(quality.projection_kind)  # type: ignore[index]
                if target is None:
                    bump(robot_id, "ignored_quality")
                    write_record(record)
                    return

                record["accepted_topic"] = target["accepted_topic"]
                if not decision.publish:
                    bump(robot_id, "rejected")
                    write_record(record)
                    return

                if args.identity_mode == "payload":
                    publish_from_payload(ctx, quality, record, target)
                    return

                signature = quality.projection_signature
                if not signature:
                    bump(robot_id, "missing_signature")
                    write_record(
                        record
                        | {
                            "status": "missing_projection_signature",
                            "reason": "quality envelope has no projection_signature",
                            "publish": False,
                        }
                    )
                    return
                key = (str(quality.projection_topic), signature)
                ctx["pending_quality"][key].append(quality)  # type: ignore[index]
                trim_pending(ctx, ctx["pending_quality"][key])  # type: ignore[index]
                drain_signature_key(ctx, key)

            return _callback

        def qualified_odom_callback_for(ctx: Mapping[str, object]):
            def _callback(message) -> None:
                nonlocal last_activity
                robot_id = str(ctx["robot_id"])
                last_activity = time.monotonic()
                bump(robot_id, "qualified_odom")
                publish_from_wrapper(
                    ctx,
                    quality_from_ros_message(message.quality),
                    message.sample,
                    ctx["target_by_kind"]["typed_odom"]["publisher"],  # type: ignore[index]
                    str(ctx["accepted_odom_topic"]),
                    "typed_odom",
                )

            return _callback

        def qualified_scan_callback_for(ctx: Mapping[str, object]):
            def _callback(message) -> None:
                nonlocal last_activity
                robot_id = str(ctx["robot_id"])
                last_activity = time.monotonic()
                bump(robot_id, "qualified_scan")
                publish_from_wrapper(
                    ctx,
                    quality_from_ros_message(message.quality),
                    message.sample,
                    ctx["target_by_kind"]["typed_scan"]["publisher"],  # type: ignore[index]
                    str(ctx["accepted_scan_topic"]),
                    "typed_scan",
                )

            return _callback

        def publish_from_wrapper(
            ctx: Mapping[str, object],
            quality: ProjectionQuality,
            sample: object,
            publisher,
            accepted_topic: str,
            projection_stream: str,
        ) -> None:
            robot_id = str(ctx["robot_id"])
            decision = ctx["gate"].evaluate(quality)  # type: ignore[union-attr]
            record = decision.as_log_record()
            record["event_type"] = "qualified_projection"
            record["robot_id"] = record.get("robot_id") or robot_id
            record["accepted_topic"] = accepted_topic
            record["projection_stream"] = projection_stream
            record["projection_identity_mode"] = "wrapper"
            record["quality_message_mode"] = "wrapped"
            record["projection_signature_match"] = True
            if decision.publish:
                publisher.publish(sample)
                bump(robot_id, "published")
            else:
                bump(robot_id, "rejected")
            bump(robot_id, "matched")
            write_record(record)

        def publish_from_payload(
            ctx: Mapping[str, object],
            quality: ProjectionQuality,
            record: dict[str, object],
            target: Mapping[str, object],
        ) -> None:
            robot_id = str(ctx["robot_id"])
            try:
                accepted_message = target["payload_factory"](quality.projection_payload)  # type: ignore[operator]
            except ValueError as exc:
                bump(robot_id, "invalid_payload")
                write_record(
                    record
                    | {
                        "status": "invalid_projection_payload",
                        "reason": str(exc),
                        "publish": False,
                    }
                )
                return
            target["publisher"].publish(accepted_message)  # type: ignore[union-attr]
            bump(robot_id, "published")
            write_record(record | {"projection_signature_match": None})

        def drain_signature_key(ctx: Mapping[str, object], key: tuple[str, str]) -> None:
            robot_id = str(ctx["robot_id"])
            pending_quality = ctx["pending_quality"]  # type: ignore[assignment]
            pending_messages = ctx["pending_messages"]  # type: ignore[assignment]
            while pending_quality[key] and pending_messages[key]:
                quality = pending_quality[key].popleft()
                message = pending_messages[key].popleft()
                target = ctx["target_by_kind"][quality.projection_kind]  # type: ignore[index]
                decision = ctx["gate"].evaluate(quality)  # type: ignore[union-attr]
                record = decision.as_log_record()
                record["event_type"] = "signature_matched_projection"
                record["robot_id"] = record.get("robot_id") or robot_id
                record["accepted_topic"] = target["accepted_topic"]
                record["projection_identity_mode"] = "signature"
                record["quality_message_mode"] = args.quality_message_mode
                record["projection_signature_match"] = True
                if decision.publish:
                    target["publisher"].publish(message)  # type: ignore[union-attr]
                    bump(robot_id, "published")
                else:
                    bump(robot_id, "rejected")
                bump(robot_id, "matched")
                write_record(record)

        def trim_pending(ctx: Mapping[str, object], queue: deque) -> None:
            robot_id = str(ctx["robot_id"])
            while len(queue) > args.max_pending_per_signature:
                queue.popleft()
                bump(robot_id, "evicted")

        def enqueue_message(ctx: Mapping[str, object], projection_topic: str, signature: str, message: object) -> None:
            nonlocal last_activity
            last_activity = time.monotonic()
            key = (projection_topic, signature)
            ctx["pending_messages"][key].append(message)  # type: ignore[index]
            trim_pending(ctx, ctx["pending_messages"][key])  # type: ignore[index]
            drain_signature_key(ctx, key)

        def odom_callback_for(ctx: Mapping[str, object]):
            def _callback(message: Odometry) -> None:
                robot_id = str(ctx["robot_id"])
                bump(robot_id, "odom")
                enqueue_message(ctx, str(ctx["odom_topic"]), projection_signature_for_odometry_message(message), message)

            return _callback

        def scan_callback_for(ctx: Mapping[str, object]):
            def _callback(message: LaserScan) -> None:
                robot_id = str(ctx["robot_id"])
                bump(robot_id, "scan")
                enqueue_message(ctx, str(ctx["scan_topic"]), projection_signature_for_laser_scan_message(message), message)

            return _callback

        subscriptions = []
        for ctx in contexts:
            if args.identity_mode == "wrapper":
                if QualifiedOdometry is None or QualifiedLaserScan is None:
                    raise SystemExit("fleetrmw_interfaces QualifiedOdometry and QualifiedLaserScan are required for wrapper identity mode")
                subscriptions.extend(
                    [
                        node.create_subscription(
                            QualifiedOdometry,
                            str(ctx["qualified_odom_topic"]),
                            qualified_odom_callback_for(ctx),
                            10,
                        ),
                        node.create_subscription(
                            QualifiedLaserScan,
                            str(ctx["qualified_scan_topic"]),
                            qualified_scan_callback_for(ctx),
                            10,
                        ),
                    ]
                )
            else:
                quality_msg_cls = ProjectionQualityMsg if args.quality_message_mode == "typed" else String
                subscriptions.append(
                    node.create_subscription(
                        quality_msg_cls,
                        str(ctx["quality_topic"]),
                        quality_callback_for(ctx),
                        10,
                    )
                )
            if args.identity_mode == "signature":
                subscriptions.extend(
                    [
                        node.create_subscription(Odometry, str(ctx["odom_topic"]), odom_callback_for(ctx), 10),
                        node.create_subscription(LaserScan, str(ctx["scan_topic"]), scan_callback_for(ctx), 10),
                    ]
                )
        try:
            while True:
                now = time.monotonic()
                if now - started > args.max_runtime_s:
                    break
                if sum(counters.values()) and now - last_activity > args.idle_timeout_s:
                    break
                rclpy.spin_once(node, timeout_sec=0.1)
        finally:
            sent, failed = flush_feedback_window(
                args,
                feedback_window,
                force=True,
                feedback_client=feedback_client,
            )
            counters["feedback_sent"] += sent
            counters["feedback_failed"] += failed
            if feedback_client is not None:
                feedback_client.close()
            for subscription in subscriptions:
                node.destroy_subscription(subscription)
            node.destroy_node()
            rclpy.shutdown()

    print(
        "projection_quality_gate "
        f"robot_count={len(robot_ids)} "
        f"mode={args.identity_mode} quality_msg={args.quality_message_mode} "
        f"quality={counters['quality']} odom={counters['odom']} scan={counters['scan']} "
        f"qualified_odom={counters['qualified_odom']} qualified_scan={counters['qualified_scan']} "
        f"matched={counters['matched']} published={counters['published']} ignored_quality={counters['ignored_quality']} "
        f"rejected={counters['rejected']} invalid_quality={counters['invalid_quality']} "
        f"invalid_payload={counters['invalid_payload']} missing_signature={counters['missing_signature']} "
        f"feedback_sent={counters['feedback_sent']} feedback_failed={counters['feedback_failed']} "
        f"evicted={counters['evicted']} "
        f"by_robot={{{', '.join(f'{robot}:dict({dict(counts)})' for robot, counts in counters_by_robot.items())}}}"
    )


def quality_gate_feedback_record(
    record: dict[str, object],
) -> dict[str, object] | None:
    robot_id = str(record.get("robot_id", "") or "")
    projection_kind = str(record.get("projection_kind", "") or "")
    if not robot_id or not projection_kind:
        return None
    if str(record.get("status", "")) == "ignore_projection_kind":
        return None

    published = bool(record.get("publish"))
    feedback: dict[str, object] = {
        "schema_version": "fleetrmw.robot_feedback.v1",
        "source": "projection_quality_gate",
        "robot_id": robot_id,
        "flow_id": str(record.get("flow_id", "") or ""),
        "flow_class": projection_feedback_flow_class(projection_kind),
        "event_type": "projection_quality",
        "event_id": record.get("event_id"),
        "qoe_risk": 0.0 if published else 1.0,
        "projection_publish": published,
        "projection_status": str(record.get("status", "") or ""),
        "feedback_sample_count": 1,
    }
    age_ms = feedback_float(record.get("age_ms"))
    deadline_ms = feedback_float(record.get("deadline_ms"))
    if age_ms is not None:
        feedback["tail_latency_ms"] = age_ms
    if deadline_ms is not None:
        feedback["mean_deadline_ms"] = deadline_ms
        if age_ms is not None and deadline_ms > 0.0:
            feedback["latency_deadline_ratio"] = age_ms / deadline_ms
    return feedback


def projection_feedback_flow_class(projection_kind: str) -> str:
    if projection_kind == "typed_odom":
        return "state"
    if projection_kind == "typed_scan":
        return "perception"
    return "human_qoe"


def flush_feedback_window(
    args: argparse.Namespace,
    records: list[dict[str, object]],
    *,
    force: bool = False,
    feedback_client: RobotFeedbackTcpClient | None = None,
) -> tuple[int, int]:
    if not args.feedback_sidecar_host:
        records.clear()
        return 0, 0
    every = max(1, int(args.feedback_every_decisions))
    if not force and len(records) < every:
        return 0, 0
    if not records:
        return 0, 0
    batch = list(records)
    records.clear()
    try:
        if feedback_client is not None:
            response = feedback_client.send_feedback(batch)
        else:
            response = send_robot_feedback(
                host=args.feedback_sidecar_host,
                port=args.feedback_sidecar_port,
                records=batch,
                timeout_s=args.feedback_timeout_s,
            )
        return int(response.get("applied", 0)), 0
    except (OSError, TimeoutError, json.JSONDecodeError):
        return 0, 1


def feedback_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def robot_ids_for_args(base_robot_id: str, robot_count: int) -> list[str]:
    if robot_count <= 0:
        raise SystemExit("--robot-count must be positive")
    if robot_count == 1:
        return [base_robot_id]
    return [f"robot_{index:04d}" for index in range(robot_count)]


def topic_for_robot(
    explicit_topic: str | None,
    *,
    default_template: str,
    base_robot_id: str,
    robot_id: str,
) -> str:
    topic = explicit_topic or default_template
    if "{robot_id}" in topic:
        return topic.format(robot_id=robot_id)
    if base_robot_id in topic:
        return topic.replace(base_robot_id, robot_id)
    if "robot_0000" in topic:
        return topic.replace("robot_0000", robot_id)
    if robot_id == base_robot_id:
        return topic
    raise SystemExit(
        "multi-robot topics must include {robot_id}, the base robot id, or robot_0000"
    )


def quality_from_ros_message(message: object) -> ProjectionQuality:
    if hasattr(message, "data"):
        return ProjectionQuality.from_payload(message.data)
    return ProjectionQuality.from_payload(projection_quality_payload_from_message(message))


def projection_signature_for_odometry_message(message: object) -> str:
    return projection_signature("typed_odom", odometry_projection_payload_from_message(message))


def projection_signature_for_laser_scan_message(message: object) -> str:
    return projection_signature("typed_scan", laser_scan_projection_payload_from_message(message))


def odometry_projection_payload_from_message(message: object) -> dict[str, object]:
    return {
        "header": header_payload_from_message(message.header),
        "odometry": {
            "child_frame_id": str(message.child_frame_id),
            "pose": {
                "position": vector_payload_from_message(message.pose.pose.position),
                "orientation": quaternion_payload_from_message(message.pose.pose.orientation),
                "covariance": list(message.pose.covariance),
            },
            "twist": {
                "linear": vector_payload_from_message(message.twist.twist.linear),
                "angular": vector_payload_from_message(message.twist.twist.angular),
                "covariance": list(message.twist.covariance),
            },
        },
    }


def laser_scan_projection_payload_from_message(message: object) -> dict[str, object]:
    return {
        "header": header_payload_from_message(message.header),
        "scan": {
            "angle_min": message.angle_min,
            "angle_max": message.angle_max,
            "angle_increment": message.angle_increment,
            "time_increment": message.time_increment,
            "scan_time": message.scan_time,
            "range_min": message.range_min,
            "range_max": message.range_max,
            "ranges": list(message.ranges),
            "intensities": list(message.intensities),
        },
    }


def header_payload_from_message(header: object) -> dict[str, object]:
    return {
        "frame_id": str(header.frame_id),
        "stamp": {
            "sec": _int_value(header.stamp.sec),
            "nanosec": _int_value(header.stamp.nanosec),
        },
    }


def vector_payload_from_message(vector: object) -> dict[str, object]:
    return {
        "x": vector.x,
        "y": vector.y,
        "z": vector.z,
    }


def quaternion_payload_from_message(quaternion: object) -> dict[str, object]:
    return {
        "x": quaternion.x,
        "y": quaternion.y,
        "z": quaternion.z,
        "w": quaternion.w,
    }


def odometry_from_projection_payload(odom_cls, payload: Mapping[str, object]):
    data = _mapping(payload)
    odom = _mapping(data.get("odometry"))
    if not odom:
        raise ValueError("typed_odom projection_payload missing odometry")

    message = odom_cls()
    _assign_header(message.header, data.get("header", {}))
    message.child_frame_id = str(odom.get("child_frame_id", ""))
    pose = _mapping(odom.get("pose"))
    twist = _mapping(odom.get("twist"))
    _assign_vector(message.pose.pose.position, pose.get("position", {}))
    _assign_quaternion(message.pose.pose.orientation, pose.get("orientation", {}))
    _assign_covariance(message.pose.covariance, pose.get("covariance", []))
    _assign_vector(message.twist.twist.linear, twist.get("linear", {}))
    _assign_vector(message.twist.twist.angular, twist.get("angular", {}))
    _assign_covariance(message.twist.covariance, twist.get("covariance", []))
    return message


def laser_scan_from_projection_payload(scan_cls, payload: Mapping[str, object]):
    data = _mapping(payload)
    scan = _mapping(data.get("scan"))
    if not scan:
        raise ValueError("typed_scan projection_payload missing scan")

    message = scan_cls()
    _assign_header(message.header, data.get("header", {}))
    message.angle_min = _float_value(scan.get("angle_min"))
    message.angle_max = _float_value(scan.get("angle_max"))
    message.angle_increment = _float_value(scan.get("angle_increment"))
    message.time_increment = _float_value(scan.get("time_increment"))
    message.scan_time = _float_value(scan.get("scan_time"))
    message.range_min = _float_value(scan.get("range_min"))
    message.range_max = _float_value(scan.get("range_max"))
    message.ranges = [_float_value(item) for item in _sequence(scan.get("ranges"))]
    message.intensities = [_float_value(item) for item in _sequence(scan.get("intensities"))]
    return message


def _assign_header(header, payload: object) -> None:
    data = _mapping(payload)
    stamp = _mapping(data.get("stamp"))
    header.stamp.sec = _int_value(stamp.get("sec"))
    header.stamp.nanosec = _int_value(stamp.get("nanosec"))
    header.frame_id = str(data.get("frame_id", ""))


def _assign_vector(vector, payload: object) -> None:
    data = _mapping(payload)
    vector.x = _float_value(data.get("x"))
    vector.y = _float_value(data.get("y"))
    vector.z = _float_value(data.get("z"))


def _assign_quaternion(quaternion, payload: object) -> None:
    data = _mapping(payload)
    quaternion.x = _float_value(data.get("x"))
    quaternion.y = _float_value(data.get("y"))
    quaternion.z = _float_value(data.get("z"))
    quaternion.w = _float_value(data.get("w"), default=1.0)


def _assign_covariance(target, payload: object) -> None:
    values = [_float_value(item) for item in _sequence(payload)[:36]]
    for index, value in enumerate(values):
        target[index] = value


def _mapping(value: object) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list:
    if isinstance(value, list | tuple):
        return list(value)
    return []


def _float_value(value: object, *, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _int_value(value: object) -> int:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    main()
