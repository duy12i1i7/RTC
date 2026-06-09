"""Monitor ROS 2 std_msgs/String topics and write observed messages as JSONL."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from fleetqox.projection_quality_ros import projection_quality_payload_from_message


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robot-id", default="robot_0000")
    parser.add_argument("--robot-count", type=int, default=1)
    parser.add_argument("--topic", action="append", required=True)
    parser.add_argument("--quality-topic", action="append", default=[])
    parser.add_argument("--qualified-odom-topic", action="append", default=[])
    parser.add_argument("--qualified-scan-topic", action="append", default=[])
    parser.add_argument("--twist-topic", action="append", default=[])
    parser.add_argument("--odom-topic", action="append", default=[])
    parser.add_argument("--scan-topic", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node-name", default="fleetrmw_string_monitor")
    parser.add_argument("--idle-timeout-s", type=float, default=4.0)
    parser.add_argument("--max-runtime-s", type=float, default=120.0)
    args = parser.parse_args()

    try:
        import rclpy
        from geometry_msgs.msg import Twist
        from fleetrmw_interfaces.msg import ProjectionQuality
        from fleetrmw_interfaces.msg import QualifiedLaserScan, QualifiedOdometry
        from nav_msgs.msg import Odometry
        from sensor_msgs.msg import LaserScan
        from std_msgs.msg import String
    except ImportError as exc:
        raise SystemExit(
            "ROS 2 rclpy, geometry_msgs, fleetrmw_interfaces, nav_msgs, sensor_msgs, and std_msgs are required for topic monitor"
        ) from exc

    args.topic = expand_topics_for_robots(args.topic, args.robot_id, args.robot_count)
    args.quality_topic = expand_topics_for_robots(args.quality_topic, args.robot_id, args.robot_count)
    args.qualified_odom_topic = expand_topics_for_robots(args.qualified_odom_topic, args.robot_id, args.robot_count)
    args.qualified_scan_topic = expand_topics_for_robots(args.qualified_scan_topic, args.robot_id, args.robot_count)
    args.twist_topic = expand_topics_for_robots(args.twist_topic, args.robot_id, args.robot_count)
    args.odom_topic = expand_topics_for_robots(args.odom_topic, args.robot_id, args.robot_count)
    args.scan_topic = expand_topics_for_robots(args.scan_topic, args.robot_id, args.robot_count)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    node = rclpy.create_node(args.node_name)

    started = time.monotonic()
    last_message = started
    count = 0

    with args.output.open("w", encoding="utf-8") as handle:

        def callback_for(topic: str):
            def _callback(message: String) -> None:
                nonlocal count, last_message
                count += 1
                last_message = time.monotonic()
                handle.write(json.dumps(monitor_record(topic=topic, data=message.data), sort_keys=True) + "\n")
                handle.flush()

            return _callback

        def twist_callback_for(topic: str):
            def _callback(message: Twist) -> None:
                nonlocal count, last_message
                count += 1
                last_message = time.monotonic()
                handle.write(json.dumps(twist_monitor_record(topic=topic, message=message), sort_keys=True) + "\n")
                handle.flush()

            return _callback

        def quality_callback_for(topic: str):
            def _callback(message: ProjectionQuality) -> None:
                nonlocal count, last_message
                count += 1
                last_message = time.monotonic()
                handle.write(json.dumps(quality_monitor_record(topic=topic, message=message), sort_keys=True) + "\n")
                handle.flush()

            return _callback

        def odom_callback_for(topic: str):
            def _callback(message: Odometry) -> None:
                nonlocal count, last_message
                count += 1
                last_message = time.monotonic()
                handle.write(json.dumps(odom_monitor_record(topic=topic, message=message), sort_keys=True) + "\n")
                handle.flush()

            return _callback

        def qualified_odom_callback_for(topic: str):
            def _callback(message: QualifiedOdometry) -> None:
                nonlocal count, last_message
                count += 1
                last_message = time.monotonic()
                handle.write(json.dumps(qualified_odom_monitor_record(topic=topic, message=message), sort_keys=True) + "\n")
                handle.flush()

            return _callback

        def scan_callback_for(topic: str):
            def _callback(message: LaserScan) -> None:
                nonlocal count, last_message
                count += 1
                last_message = time.monotonic()
                handle.write(json.dumps(scan_monitor_record(topic=topic, message=message), sort_keys=True) + "\n")
                handle.flush()

            return _callback

        def qualified_scan_callback_for(topic: str):
            def _callback(message: QualifiedLaserScan) -> None:
                nonlocal count, last_message
                count += 1
                last_message = time.monotonic()
                handle.write(json.dumps(qualified_scan_monitor_record(topic=topic, message=message), sort_keys=True) + "\n")
                handle.flush()

            return _callback

        subscriptions = [node.create_subscription(String, topic, callback_for(topic), 10) for topic in args.topic]
        subscriptions.extend(
            node.create_subscription(ProjectionQuality, topic, quality_callback_for(topic), 10)
            for topic in args.quality_topic
        )
        subscriptions.extend(
            node.create_subscription(Twist, topic, twist_callback_for(topic), 10)
            for topic in args.twist_topic
        )
        subscriptions.extend(
            node.create_subscription(Odometry, topic, odom_callback_for(topic), 10)
            for topic in args.odom_topic
        )
        subscriptions.extend(
            node.create_subscription(QualifiedOdometry, topic, qualified_odom_callback_for(topic), 10)
            for topic in args.qualified_odom_topic
        )
        subscriptions.extend(
            node.create_subscription(LaserScan, topic, scan_callback_for(topic), 10)
            for topic in args.scan_topic
        )
        subscriptions.extend(
            node.create_subscription(QualifiedLaserScan, topic, qualified_scan_callback_for(topic), 10)
            for topic in args.qualified_scan_topic
        )
        try:
            while True:
                now = time.monotonic()
                if now - started > args.max_runtime_s:
                    break
                if count and now - last_message > args.idle_timeout_s:
                    break
                rclpy.spin_once(node, timeout_sec=0.1)
        finally:
            for subscription in subscriptions:
                node.destroy_subscription(subscription)
            node.destroy_node()
            rclpy.shutdown()

    print(f"monitored {count} ROS 2 messages")


def monitor_record(*, topic: str, data: str) -> dict[str, object]:
    record: dict[str, object] = {
        "topic": topic,
        "msg_type": "std_msgs/msg/String",
        "data": data,
        "recv_monotonic_ns": time.monotonic_ns(),
    }
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return record
    if isinstance(payload, dict):
        record["kind"] = payload.get("kind")
        record["contract_id"] = payload.get("contract_id")
        record["source_sample_id"] = payload.get("source_sample_id")
        record["event_id"] = payload.get("event_id")
        record["robot_id"] = payload.get("robot_id")
        record["flow_id"] = payload.get("flow_id")
        record["source_topic"] = payload.get("source_topic")
        record["projection_kind"] = payload.get("projection_kind")
        record["projection_topic"] = payload.get("projection_topic")
        record["projection_msg_type"] = payload.get("projection_msg_type")
        record["fidelity_class"] = payload.get("fidelity_class")
        record["lossy"] = payload.get("lossy")
        record["projection_signature"] = payload.get("projection_signature")
        record["projection_payload_embedded"] = payload.get("projection_payload_embedded")
    return record


def quality_monitor_record(*, topic: str, message) -> dict[str, object]:
    payload = projection_quality_payload_from_message(message)
    return {
        "topic": topic,
        "msg_type": "fleetrmw_interfaces/msg/ProjectionQuality",
        "kind": payload.get("kind"),
        "contract_id": payload.get("contract_id"),
        "source_sample_id": payload.get("source_sample_id"),
        "event_id": payload.get("event_id"),
        "robot_id": payload.get("robot_id"),
        "flow_id": payload.get("flow_id"),
        "source_topic": payload.get("source_topic"),
        "projection_kind": payload.get("projection_kind"),
        "projection_topic": payload.get("projection_topic"),
        "projection_msg_type": payload.get("projection_msg_type"),
        "fidelity_class": payload.get("fidelity_class"),
        "lossy": payload.get("lossy"),
        "projection_signature": payload.get("projection_signature"),
        "projection_payload_embedded": payload.get("projection_payload_embedded"),
        "recv_monotonic_ns": time.monotonic_ns(),
    }


def twist_monitor_record(*, topic: str, message) -> dict[str, object]:
    return {
        "topic": topic,
        "msg_type": "geometry_msgs/msg/Twist",
        "kind": "typed_twist",
        "recv_monotonic_ns": time.monotonic_ns(),
        "linear": {
            "x": float(message.linear.x),
            "y": float(message.linear.y),
            "z": float(message.linear.z),
        },
        "angular": {
            "x": float(message.angular.x),
            "y": float(message.angular.y),
            "z": float(message.angular.z),
        },
    }


def odom_monitor_record(*, topic: str, message) -> dict[str, object]:
    return {
        "topic": topic,
        "msg_type": "nav_msgs/msg/Odometry",
        "kind": "typed_odom",
        "recv_monotonic_ns": time.monotonic_ns(),
        "frame_id": str(message.header.frame_id),
        "child_frame_id": str(message.child_frame_id),
        "position": {
            "x": float(message.pose.pose.position.x),
            "y": float(message.pose.pose.position.y),
            "z": float(message.pose.pose.position.z),
        },
        "linear": {
            "x": float(message.twist.twist.linear.x),
            "y": float(message.twist.twist.linear.y),
            "z": float(message.twist.twist.linear.z),
        },
    }


def qualified_odom_monitor_record(*, topic: str, message) -> dict[str, object]:
    record = odom_monitor_record(topic=topic, message=message.sample)
    quality = projection_quality_payload_from_message(message.quality)
    record.update(
        {
            "msg_type": "fleetrmw_interfaces/msg/QualifiedOdometry",
            "kind": "qualified_odom",
            "contract_id": quality.get("contract_id"),
            "source_sample_id": quality.get("source_sample_id"),
            "event_id": quality.get("event_id"),
            "projection_kind": quality.get("projection_kind"),
            "fidelity_class": quality.get("fidelity_class"),
            "projection_signature": quality.get("projection_signature"),
            "projection_payload_embedded": quality.get("projection_payload_embedded"),
        }
    )
    return record


def scan_monitor_record(*, topic: str, message) -> dict[str, object]:
    ranges = list(message.ranges)
    return {
        "topic": topic,
        "msg_type": "sensor_msgs/msg/LaserScan",
        "kind": "typed_scan",
        "recv_monotonic_ns": time.monotonic_ns(),
        "frame_id": str(message.header.frame_id),
        "angle_min": float(message.angle_min),
        "angle_max": float(message.angle_max),
        "range_count": len(ranges),
        "range_min_observed": float(min(ranges)) if ranges else None,
        "range_max_observed": float(max(ranges)) if ranges else None,
    }


def qualified_scan_monitor_record(*, topic: str, message) -> dict[str, object]:
    record = scan_monitor_record(topic=topic, message=message.sample)
    quality = projection_quality_payload_from_message(message.quality)
    record.update(
        {
            "msg_type": "fleetrmw_interfaces/msg/QualifiedLaserScan",
            "kind": "qualified_scan",
            "contract_id": quality.get("contract_id"),
            "source_sample_id": quality.get("source_sample_id"),
            "event_id": quality.get("event_id"),
            "projection_kind": quality.get("projection_kind"),
            "fidelity_class": quality.get("fidelity_class"),
            "projection_signature": quality.get("projection_signature"),
            "projection_payload_embedded": quality.get("projection_payload_embedded"),
        }
    )
    return record


def expand_topics_for_robots(topics: list[str], base_robot_id: str, robot_count: int) -> list[str]:
    if robot_count <= 0:
        raise SystemExit("--robot-count must be positive")
    if robot_count == 1:
        return list(topics)
    expanded: list[str] = []
    seen: set[str] = set()
    for robot_index in range(robot_count):
        robot_id = f"robot_{robot_index:04d}"
        for topic in topics:
            expanded_topic = topic_for_robot(topic, base_robot_id=base_robot_id, robot_id=robot_id)
            if expanded_topic not in seen:
                expanded.append(expanded_topic)
                seen.add(expanded_topic)
    return expanded


def topic_for_robot(topic: str, *, base_robot_id: str, robot_id: str) -> str:
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


if __name__ == "__main__":
    main()
