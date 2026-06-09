"""Publish a small ROS 2 topic set for FleetRMW live-bridge integration tests."""

from __future__ import annotations

import argparse
import math
import random
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RobotPublisherSet:
    robot_id: str
    cmd_pub: object
    odom_pub: object
    scan_pub: object
    camera_pub: object
    phase_offset: float
    speed_offset: float


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robot-id", default="robot_0000")
    parser.add_argument("--robot-count", type=int, default=1)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--rate-hz", type=float, default=20.0)
    parser.add_argument("--cmd-topic", default="/robot_0000/cmd_vel")
    parser.add_argument("--odom-topic", default="/robot_0000/odom")
    parser.add_argument("--scan-topic", default="/robot_0000/scan")
    parser.add_argument("--camera-topic", default="/robot_0000/front_camera/image_raw/compressed")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    try:
        import rclpy
        from geometry_msgs.msg import Twist
        from nav_msgs.msg import Odometry
        from rclpy.duration import Duration
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import CompressedImage, LaserScan
    except ImportError as exc:
        raise SystemExit(
            "run_ros2_test_publisher requires a sourced ROS 2 environment with "
            "geometry_msgs, nav_msgs, and sensor_msgs"
        ) from exc
    if args.robot_count <= 0:
        raise SystemExit("--robot-count must be positive")

    rclpy.init()
    node = rclpy.create_node("fleetrmw_test_publisher")
    publishers = [
        _publisher_set_for_robot(
            node,
            robot_id=_robot_id_for_index(args.robot_id, index),
            args=args,
            seed=args.seed + index * 7919,
            twist_cls=Twist,
            odom_cls=Odometry,
            scan_cls=LaserScan,
            camera_cls=CompressedImage,
            qos_profile_cls=QoSProfile,
            reliability_policy_cls=ReliabilityPolicy,
            duration_cls=Duration,
        )
        for index in range(args.robot_count)
    ]

    period_s = 1.0 / max(args.rate_hz, 0.001)
    start = time.monotonic()
    sent = 0
    try:
        while time.monotonic() - start < args.seconds:
            stamp = node.get_clock().now().to_msg()
            for robot_index, publisher in enumerate(publishers):
                phase = publisher.phase_offset + sent * 0.05
                cmd = Twist()
                cmd.linear.x = 0.2 + publisher.speed_offset + 0.02 * math.sin(phase)
                cmd.angular.z = 0.1 * math.cos(phase)
                publisher.cmd_pub.publish(cmd)

                odom = Odometry()
                odom.header.stamp = stamp
                odom.header.frame_id = "odom"
                odom.child_frame_id = publisher.robot_id
                odom.pose.pose.position.x = 0.01 * sent
                odom.pose.pose.position.y = 0.35 * robot_index
                odom.twist.twist.linear.x = cmd.linear.x
                publisher.odom_pub.publish(odom)

                scan = LaserScan()
                scan.header.stamp = stamp
                scan.header.frame_id = f"{publisher.robot_id}/base_scan"
                scan.angle_min = -1.57
                scan.angle_max = 1.57
                scan.angle_increment = 0.0175
                scan.range_min = 0.12
                scan.range_max = 8.0
                scan.ranges = [
                    2.0 + 0.2 * math.sin(phase + idx * 0.1)
                    for idx in range(180)
                ]
                publisher.scan_pub.publish(scan)

                image = CompressedImage()
                image.header.stamp = stamp
                image.header.frame_id = f"{publisher.robot_id}/front_camera"
                image.format = "jpeg"
                image.data = bytes((idx + sent + args.seed + robot_index) % 251 for idx in range(2048))
                publisher.camera_pub.publish(image)

            sent += 1
            rclpy.spin_once(node, timeout_sec=0.0)
            time.sleep(period_s)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    print(
        {
            "status": "ok",
            "sent_ticks": sent,
            "robot_count": args.robot_count,
            "published_messages": sent * args.robot_count * 4,
        }
    )


def _publisher_set_for_robot(
    node,
    *,
    robot_id: str,
    args: argparse.Namespace,
    seed: int,
    twist_cls,
    odom_cls,
    scan_cls,
    camera_cls,
    qos_profile_cls,
    reliability_policy_cls,
    duration_cls,
) -> RobotPublisherSet:
    rng = random.Random(seed)
    return RobotPublisherSet(
        robot_id=robot_id,
        cmd_pub=node.create_publisher(
            twist_cls,
            _topic_for_robot(args.cmd_topic, robot_id),
            _qos(qos_profile_cls, reliability_policy_cls, duration_cls, 1, "reliable", 45, 90),
        ),
        odom_pub=node.create_publisher(
            odom_cls,
            _topic_for_robot(args.odom_topic, robot_id),
            _qos(qos_profile_cls, reliability_policy_cls, duration_cls, 3, "reliable", 120, 350),
        ),
        scan_pub=node.create_publisher(
            scan_cls,
            _topic_for_robot(args.scan_topic, robot_id),
            _qos(qos_profile_cls, reliability_policy_cls, duration_cls, 1, "best_effort", 160, 300),
        ),
        camera_pub=node.create_publisher(
            camera_cls,
            _topic_for_robot(args.camera_topic, robot_id),
            _qos(qos_profile_cls, reliability_policy_cls, duration_cls, 1, "best_effort", 120, 180),
        ),
        phase_offset=rng.random() * math.tau,
        speed_offset=rng.uniform(-0.01, 0.01),
    )


def _robot_id_for_index(base_robot_id: str, index: int) -> str:
    if index == 0:
        return base_robot_id
    if base_robot_id == "robot_0000":
        return f"robot_{index:04d}"
    return f"{base_robot_id}_{index:04d}"


def _topic_for_robot(template: str, robot_id: str) -> str:
    if "{robot_id}" in template:
        return template.format(robot_id=robot_id)
    if "robot_0000" in template:
        return template.replace("robot_0000", robot_id)
    if template.startswith("/"):
        return f"/{robot_id}{template}"
    return f"/{robot_id}/{template}"


def _qos(qos_profile_cls, reliability_policy_cls, duration_cls, depth: int, reliability: str, deadline_ms: float, lifespan_ms: float):
    profile = qos_profile_cls(depth=depth)
    profile.reliability = (
        reliability_policy_cls.RELIABLE
        if reliability == "reliable"
        else reliability_policy_cls.BEST_EFFORT
    )
    profile.deadline = _duration_from_ms(duration_cls, deadline_ms)
    profile.lifespan = _duration_from_ms(duration_cls, lifespan_ms)
    return profile


def _duration_from_ms(duration_cls, ms: float):
    nanoseconds = int(ms * 1_000_000)
    seconds = nanoseconds // 1_000_000_000
    remainder = nanoseconds % 1_000_000_000
    return duration_cls(seconds=seconds, nanoseconds=remainder)


if __name__ == "__main__":
    main()
