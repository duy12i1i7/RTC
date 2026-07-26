"""rclpy half of the FleetRMW C++/Python interprocess interoperability probe."""

from __future__ import annotations

import copy
import json
import math
import sys
import time
from typing import Any

import rclpy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Path
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_srvs.srv import SetBool


SCHEMA_VERSION = "fleetrmw.rclpy_cpp_interprocess_endpoint.v1"
PATH_POSE_COUNT = 64
QOS = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)


def make_path_request() -> Path:
    path = Path()
    path.header.stamp.sec = -11
    path.header.stamp.nanosec = 987654321
    path.header.frame_id = "fleet/path"
    for index in range(PATH_POSE_COUNT):
        pose = PoseStamped()
        pose.header.stamp.sec = index - 32
        pose.header.stamp.nanosec = index * 1_000_000
        pose.header.frame_id = f"fleet/path/{index}"
        pose.pose.position.x = index * 0.25
        pose.pose.position.y = -index * 0.5
        pose.pose.position.z = float(index % 3)
        pose.pose.orientation.z = index / 100.0
        pose.pose.orientation.w = 1.0
        path.poses.append(pose)
    return path


def valid_path_request(path: Path) -> bool:
    if (
        path.header.stamp.sec != -11
        or path.header.stamp.nanosec != 987654321
        or path.header.frame_id != "fleet/path"
        or len(path.poses) != PATH_POSE_COUNT
    ):
        return False
    for index, pose in enumerate(path.poses):
        if (
            pose.header.stamp.sec != index - 32
            or pose.header.stamp.nanosec != index * 1_000_000
            or pose.header.frame_id != f"fleet/path/{index}"
            or not math.isclose(pose.pose.position.x, index * 0.25, abs_tol=1e-12)
            or not math.isclose(pose.pose.position.y, -index * 0.5, abs_tol=1e-12)
            or not math.isclose(pose.pose.position.z, index % 3, abs_tol=1e-12)
            or not math.isclose(pose.pose.orientation.z, index / 100.0, abs_tol=1e-12)
            or not math.isclose(pose.pose.orientation.w, 1.0, abs_tol=1e-12)
        ):
            return False
    return True


def valid_path_reply(path: Path) -> bool:
    if (
        path.header.stamp.sec != -11
        or path.header.stamp.nanosec != 987654321
        or path.header.frame_id != "fleet/path/ack"
        or len(path.poses) != PATH_POSE_COUNT
    ):
        return False
    for index, pose in enumerate(path.poses):
        if (
            pose.header.stamp.sec != index - 32
            or pose.header.stamp.nanosec != index * 1_000_000
            or pose.header.frame_id != f"fleet/path/{index}/ack"
            or not math.isclose(
                pose.pose.position.x, index * 0.25 + 100.0, abs_tol=1e-12
            )
            or not math.isclose(pose.pose.position.y, -index * 0.5, abs_tol=1e-12)
            or not math.isclose(pose.pose.orientation.z, index / 100.0, abs_tol=1e-12)
        ):
            return False
    return True


def print_summary(summary: dict[str, Any]) -> int:
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0 if summary["status"] == "ok" else 1


def run_server() -> int:
    node = rclpy.create_node(
        "fleetqox_python_interprocess_server",
        enable_rosout=False,
        start_parameter_services=False,
    )
    state = {
        "pose_received": False,
        "path_received": False,
        "path_valid": False,
        "service_received": False,
    }
    pose_publisher = node.create_publisher(
        PoseStamped, "/fleetqox/cpp_pose_reply", QOS
    )
    path_publisher = node.create_publisher(Path, "/fleetqox/cpp_path_reply", QOS)

    def on_pose(request: PoseStamped) -> None:
        reply = copy.deepcopy(request)
        reply.header.frame_id += "/ack"
        reply.pose.position.x += 1.0
        pose_publisher.publish(reply)
        state["pose_received"] = True

    def on_path(request: Path) -> None:
        state["path_received"] = True
        state["path_valid"] = valid_path_request(request)
        if not state["path_valid"]:
            return
        reply = copy.deepcopy(request)
        reply.header.frame_id += "/ack"
        for pose in reply.poses:
            pose.header.frame_id += "/ack"
            pose.pose.position.x += 100.0
        path_publisher.publish(reply)

    def on_service(request: SetBool.Request, response: SetBool.Response) -> SetBool.Response:
        state["service_received"] = True
        response.success = request.data
        response.message = "cpp-service-ok" if request.data else "cpp-service-false"
        return response

    node.create_subscription(PoseStamped, "/fleetqox/cpp_pose_request", on_pose, QOS)
    node.create_subscription(Path, "/fleetqox/cpp_path_request", on_path, QOS)
    node.create_service(SetBool, "/fleetqox/cpp_set_bool", on_service)
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline and not all(state.values()):
        rclpy.spin_once(node, timeout_sec=0.05)
    ok = all(state.values())
    summary = {
        "schema_version": SCHEMA_VERSION,
        "role": "server",
        "status": "ok" if ok else "failed",
        **state,
        "path_pose_count": PATH_POSE_COUNT,
    }
    node.destroy_node()
    return print_summary(summary)


def run_client() -> int:
    node = rclpy.create_node(
        "fleetqox_python_interprocess_client",
        enable_rosout=False,
        start_parameter_services=False,
    )
    state = {"pose_roundtrip": False, "path_roundtrip": False}
    pose_publisher = node.create_publisher(
        PoseStamped, "/fleetqox/cpp_pose_request", QOS
    )
    path_publisher = node.create_publisher(Path, "/fleetqox/cpp_path_request", QOS)

    def on_pose(reply: PoseStamped) -> None:
        state["pose_roundtrip"] = (
            reply.header.frame_id == "fleet/map/ack"
            and reply.header.stamp.sec == -7
            and reply.header.stamp.nanosec == 123456789
            and math.isclose(reply.pose.position.x, 2.25, abs_tol=1e-12)
            and math.isclose(reply.pose.position.y, -2.5, abs_tol=1e-12)
        )

    def on_path(reply: Path) -> None:
        state["path_roundtrip"] = valid_path_reply(reply)

    node.create_subscription(PoseStamped, "/fleetqox/cpp_pose_reply", on_pose, QOS)
    node.create_subscription(Path, "/fleetqox/cpp_path_reply", on_path, QOS)
    service = node.create_client(SetBool, "/fleetqox/cpp_set_bool")
    service_available = service.wait_for_service(timeout_sec=8.0)
    future = None
    if service_available:
        request = SetBool.Request()
        request.data = True
        future = service.call_async(request)

    pose = PoseStamped()
    pose.header.stamp.sec = -7
    pose.header.stamp.nanosec = 123456789
    pose.header.frame_id = "fleet/map"
    pose.pose.position.x = 1.25
    pose.pose.position.y = -2.5
    pose.pose.orientation.w = 1.0
    path = make_path_request()

    service_ok = False
    next_publish = 0.0
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline and not (
        state["pose_roundtrip"] and state["path_roundtrip"] and service_ok
    ):
        now = time.monotonic()
        if now >= next_publish:
            if not state["pose_roundtrip"]:
                pose_publisher.publish(pose)
            if not state["path_roundtrip"]:
                path_publisher.publish(path)
            next_publish = now + 0.2
        rclpy.spin_once(node, timeout_sec=0.05)
        if future is not None and future.done():
            response = future.result()
            service_ok = (
                response is not None
                and response.success
                and response.message == "cpp-service-ok"
            )

    ok = service_available and service_ok and all(state.values())
    summary = {
        "schema_version": SCHEMA_VERSION,
        "role": "client",
        "status": "ok" if ok else "failed",
        "service_available": service_available,
        "service_ok": service_ok,
        **state,
        "path_pose_count": PATH_POSE_COUNT,
    }
    node.destroy_node()
    return print_summary(summary)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    rclpy.init()
    try:
        if mode == "server":
            return run_server()
        if mode == "client":
            return run_client()
        return 2
    finally:
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
