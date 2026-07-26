"""rclpy half of the generated bounded-shape service interoperability probe."""

from __future__ import annotations

import copy
import json
import math
import sys
import time
from typing import Any

import rclpy
from fleetrmw_interfaces.srv import FleetShape
from geometry_msgs.msg import PoseStamped


SCHEMA_VERSION = "fleetrmw.bounded_shape_python_endpoint.v1"
TOKEN_SIZE = 16
RANGE_COUNT = 128
WAYPOINT_COUNT = 16
ADMITTED_INDEX_COUNT = 64


def make_request() -> FleetShape.Request:
    request = FleetShape.Request()
    request.robot_id = "robot_0042"
    request.session_token = [index * 7 for index in range(TOKEN_SIZE)]
    request.ranges = [index * 0.25 for index in range(RANGE_COUNT)]
    for index in range(WAYPOINT_COUNT):
        pose = PoseStamped()
        pose.header.stamp.sec = index - 8
        pose.header.stamp.nanosec = index * 1_000_000
        pose.header.frame_id = f"fleet/bounded/{index}"
        pose.pose.position.x = index * 1.5
        pose.pose.position.y = -index * 0.75
        pose.pose.orientation.z = index / 20.0
        pose.pose.orientation.w = 1.0
        request.waypoints.append(pose)
    request.budget.sec = -2
    request.budget.nanosec = 500000000
    return request


def valid_request(request: FleetShape.Request) -> bool:
    if (
        request.robot_id != "robot_0042"
        or len(request.session_token) != TOKEN_SIZE
        or len(request.ranges) != RANGE_COUNT
        or len(request.waypoints) != WAYPOINT_COUNT
        or request.budget.sec != -2
        or request.budget.nanosec != 500000000
    ):
        return False
    if any(value != index * 7 for index, value in enumerate(request.session_token)):
        return False
    if any(
        not math.isclose(value, index * 0.25, abs_tol=1e-6)
        for index, value in enumerate(request.ranges)
    ):
        return False
    for index, pose in enumerate(request.waypoints):
        if (
            pose.header.stamp.sec != index - 8
            or pose.header.stamp.nanosec != index * 1_000_000
            or pose.header.frame_id != f"fleet/bounded/{index}"
            or not math.isclose(pose.pose.position.x, index * 1.5, abs_tol=1e-12)
            or not math.isclose(pose.pose.position.y, -index * 0.75, abs_tol=1e-12)
            or not math.isclose(pose.pose.orientation.z, index / 20.0, abs_tol=1e-12)
        ):
            return False
    return True


def populate_response(
    request: FleetShape.Request, response: FleetShape.Response
) -> FleetShape.Response:
    response.accepted = True
    response.reason = "bounded-shape-cpp-python-ok"
    response.admitted_indices = [
        index * 2 for index in range(ADMITTED_INDEX_COUNT)
    ]
    response.repaired_waypoints = copy.deepcopy(request.waypoints)
    for pose in response.repaired_waypoints:
        pose.header.frame_id += "/repaired"
        pose.pose.position.x += 100.0
    return response


def valid_response(response: FleetShape.Response) -> bool:
    if (
        not response.accepted
        or response.reason != "bounded-shape-cpp-python-ok"
        or len(response.admitted_indices) != ADMITTED_INDEX_COUNT
        or len(response.repaired_waypoints) != WAYPOINT_COUNT
    ):
        return False
    if any(
        value != index * 2 for index, value in enumerate(response.admitted_indices)
    ):
        return False
    for index, pose in enumerate(response.repaired_waypoints):
        if (
            pose.header.frame_id != f"fleet/bounded/{index}/repaired"
            or not math.isclose(
                pose.pose.position.x, index * 1.5 + 100.0, abs_tol=1e-12
            )
            or not math.isclose(pose.pose.position.y, -index * 0.75, abs_tol=1e-12)
        ):
            return False
    return True


def output(summary: dict[str, Any]) -> int:
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0 if summary["status"] == "ok" else 1


def run_server() -> int:
    node = rclpy.create_node(
        "fleetrmw_bounded_shape_python_server",
        enable_rosout=False,
        start_parameter_services=False,
    )
    state = {"request_received": False, "request_valid": False}

    def callback(
        request: FleetShape.Request, response: FleetShape.Response
    ) -> FleetShape.Response:
        state["request_received"] = True
        state["request_valid"] = valid_request(request)
        if state["request_valid"]:
            return populate_response(request, response)
        return response

    node.create_service(FleetShape, "/fleetqox/bounded_shape", callback)
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline and not state["request_received"]:
        rclpy.spin_once(node, timeout_sec=0.05)
    ok = all(state.values())
    summary = {
        "schema_version": SCHEMA_VERSION,
        "role": "server",
        "status": "ok" if ok else "failed",
        **state,
        "token_size": TOKEN_SIZE,
        "range_count": RANGE_COUNT,
        "waypoint_count": WAYPOINT_COUNT,
    }
    node.destroy_node()
    return output(summary)


def run_client() -> int:
    node = rclpy.create_node(
        "fleetrmw_bounded_shape_python_client",
        enable_rosout=False,
        start_parameter_services=False,
    )
    client = node.create_client(FleetShape, "/fleetqox/bounded_shape")
    service_available = client.wait_for_service(timeout_sec=8.0)
    future = client.call_async(make_request()) if service_available else None
    response_valid = False
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline and not response_valid:
        rclpy.spin_once(node, timeout_sec=0.05)
        if future is not None and future.done():
            response = future.result()
            response_valid = response is not None and valid_response(response)
    ok = service_available and response_valid
    summary = {
        "schema_version": SCHEMA_VERSION,
        "role": "client",
        "status": "ok" if ok else "failed",
        "service_available": service_available,
        "response_valid": response_valid,
        "admitted_index_count": ADMITTED_INDEX_COUNT,
        "repaired_waypoint_count": WAYPOINT_COUNT,
    }
    node.destroy_node()
    return output(summary)


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
