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
from nav_msgs.srv import GetPlan
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_srvs.srv import SetBool


SCHEMA_VERSION = "fleetrmw.rclpy_cpp_interprocess_endpoint.v1"
PATH_POSE_COUNT = 64
PLAN_POSE_COUNT = 512
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


def make_plan_request() -> GetPlan.Request:
    request = GetPlan.Request()
    request.start.header.stamp.sec = -9
    request.start.header.stamp.nanosec = 111222333
    request.start.header.frame_id = "fleet/plan_map"
    request.start.pose.position.x = -2.0
    request.start.pose.position.y = 1.5
    request.start.pose.orientation.w = 1.0
    request.goal.header.stamp.sec = 19
    request.goal.header.stamp.nanosec = 444555666
    request.goal.header.frame_id = "fleet/plan_map"
    request.goal.pose.position.x = 8.0
    request.goal.pose.position.y = -3.5
    request.goal.pose.orientation.w = 1.0
    request.tolerance = 0.125
    return request


def valid_plan_request(request: GetPlan.Request) -> bool:
    return (
        request.start.header.stamp.sec == -9
        and request.start.header.stamp.nanosec == 111222333
        and request.start.header.frame_id == "fleet/plan_map"
        and math.isclose(request.start.pose.position.x, -2.0, abs_tol=1e-12)
        and math.isclose(request.start.pose.position.y, 1.5, abs_tol=1e-12)
        and request.goal.header.stamp.sec == 19
        and request.goal.header.stamp.nanosec == 444555666
        and request.goal.header.frame_id == "fleet/plan_map"
        and math.isclose(request.goal.pose.position.x, 8.0, abs_tol=1e-12)
        and math.isclose(request.goal.pose.position.y, -3.5, abs_tol=1e-12)
        and math.isclose(request.tolerance, 0.125, abs_tol=1e-6)
    )


def make_plan_response(request: GetPlan.Request) -> Path:
    plan = Path()
    plan.header.stamp = copy.deepcopy(request.goal.header.stamp)
    plan.header.frame_id = request.start.header.frame_id + "/plan"
    for index in range(PLAN_POSE_COUNT):
        ratio = index / (PLAN_POSE_COUNT - 1)
        pose = PoseStamped()
        pose.header.stamp.sec = index - 32
        pose.header.stamp.nanosec = index * 1_000_000
        pose.header.frame_id = f"{plan.header.frame_id}/{index}"
        pose.pose.position.x = request.start.pose.position.x + ratio * (
            request.goal.pose.position.x - request.start.pose.position.x
        )
        pose.pose.position.y = request.start.pose.position.y + ratio * (
            request.goal.pose.position.y - request.start.pose.position.y
        )
        pose.pose.orientation.z = ratio
        pose.pose.orientation.w = 1.0
        plan.poses.append(pose)
    return plan


def valid_plan_response(plan: Path) -> bool:
    if (
        plan.header.stamp.sec != 19
        or plan.header.stamp.nanosec != 444555666
        or plan.header.frame_id != "fleet/plan_map/plan"
        or len(plan.poses) != PLAN_POSE_COUNT
    ):
        return False
    for index, pose in enumerate(plan.poses):
        ratio = index / (PLAN_POSE_COUNT - 1)
        if (
            pose.header.stamp.sec != index - 32
            or pose.header.stamp.nanosec != index * 1_000_000
            or pose.header.frame_id != f"fleet/plan_map/plan/{index}"
            or not math.isclose(
                pose.pose.position.x, -2.0 + ratio * 10.0, abs_tol=1e-12
            )
            or not math.isclose(
                pose.pose.position.y, 1.5 - ratio * 5.0, abs_tol=1e-12
            )
            or not math.isclose(pose.pose.orientation.z, ratio, abs_tol=1e-12)
            or not math.isclose(pose.pose.orientation.w, 1.0, abs_tol=1e-12)
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
        "plan_service_received": False,
        "plan_request_valid": False,
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

    def on_plan(
        request: GetPlan.Request, response: GetPlan.Response
    ) -> GetPlan.Response:
        state["plan_service_received"] = True
        state["plan_request_valid"] = valid_plan_request(request)
        if state["plan_request_valid"]:
            response.plan = make_plan_response(request)
        return response

    node.create_subscription(PoseStamped, "/fleetqox/cpp_pose_request", on_pose, QOS)
    node.create_subscription(Path, "/fleetqox/cpp_path_request", on_path, QOS)
    node.create_service(SetBool, "/fleetqox/cpp_set_bool", on_service)
    node.create_service(GetPlan, "/fleetqox/cpp_get_plan", on_plan)
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
        "plan_pose_count": PLAN_POSE_COUNT,
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
    plan_service = node.create_client(GetPlan, "/fleetqox/cpp_get_plan")
    service_available = service.wait_for_service(timeout_sec=8.0)
    plan_service_available = plan_service.wait_for_service(timeout_sec=8.0)
    future = None
    if service_available:
        request = SetBool.Request()
        request.data = True
        future = service.call_async(request)
    plan_future = None
    if plan_service_available:
        plan_future = plan_service.call_async(make_plan_request())

    pose = PoseStamped()
    pose.header.stamp.sec = -7
    pose.header.stamp.nanosec = 123456789
    pose.header.frame_id = "fleet/map"
    pose.pose.position.x = 1.25
    pose.pose.position.y = -2.5
    pose.pose.orientation.w = 1.0
    path = make_path_request()

    service_ok = False
    plan_service_ok = False
    next_publish = 0.0
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline and not (
        state["pose_roundtrip"]
        and state["path_roundtrip"]
        and service_ok
        and plan_service_ok
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
        if plan_future is not None and plan_future.done():
            response = plan_future.result()
            plan_service_ok = (
                response is not None and valid_plan_response(response.plan)
            )

    ok = (
        service_available
        and service_ok
        and plan_service_available
        and plan_service_ok
        and all(state.values())
    )
    summary = {
        "schema_version": SCHEMA_VERSION,
        "role": "client",
        "status": "ok" if ok else "failed",
        "service_available": service_available,
        "service_ok": service_ok,
        "plan_service_available": plan_service_available,
        "plan_service_ok": plan_service_ok,
        **state,
        "path_pose_count": PATH_POSE_COUNT,
        "plan_pose_count": PLAN_POSE_COUNT,
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
