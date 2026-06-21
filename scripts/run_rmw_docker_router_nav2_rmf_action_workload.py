"""Run Nav2/RMF-compatible action semantics through the FleetRMW router."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_router_service_call_probe import parse_last_json


SCHEMA_VERSION = "fleetrmw.rmw_router_nav2_rmf_action_workload.v5"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--upstream-concurrency", type=int, default=4)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_router_nav2_rmf_action_workload_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = ROOT
    summary = run_probe(
        root=root,
        image=args.image,
        upstream_concurrency=max(args.upstream_concurrency, 1),
    )
    path = root / args.summary_json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-nav2-rmf-action-workload")
        print(f"  status: {summary['status']}")
        print(f"  nav2_compatible: {summary.get('nav2_compatible')}")
        print(f"  rmf_compatible: {summary.get('rmf_compatible')}")
        print(f"  service_frames: {summary.get('router', {}).get('service_frames')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(*, root: Path, image: str, upstream_concurrency: int = 4) -> dict[str, Any]:
    if upstream_concurrency <= 0:
        raise ValueError("upstream_concurrency must be positive")
    suffix = str(os.getpid())
    network = f"fleetrmw-nav-rmf-net-{suffix}"
    router_name = f"fleetrmw-nav-rmf-router-{suffix}"
    server_name = f"fleetrmw-nav-rmf-server-{suffix}"
    manager_name = f"fleetrmw-nav-rmf-lifecycle-manager-{suffix}"
    build_base = "/work/.tmp_fleetrmw_nav_rmf_build"
    install_base = "/work/.tmp_fleetrmw_nav_rmf_install"
    log_base = "/work/.tmp_fleetrmw_nav_rmf_log"
    expected_service_frames = 58 + upstream_concurrency * 6

    def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check
        )

    def docker_shell(command: str, *extra: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return run([
            "docker", "run", "--rm", *extra,
            "--entrypoint", "bash",
            "-v", f"{root}:/work", "-w", "/work", image, "-lc", command,
        ], check=check)

    server_python = textwrap.dedent(
        """
        import json
        import gc
        import time
        import traceback
        import rclpy
        from rclpy.action import ActionServer, CancelResponse
        from rclpy.executors import MultiThreadedExecutor
        from rclpy.lifecycle import LifecycleNode, TransitionCallbackReturn
        from fleetrmw_interfaces.action import NavigateFleet, DispatchFleetTask
        from nav2_msgs.action import NavigateToPose
        from rmf_task_msgs.srv import SubmitTask, CancelTask

        events = []
        feedback_counts = {"navigation": 0, "task": 0}
        executor = None
        node = None
        servers = []
        services = []
        lifecycle_node = None

        class ManagedNavLifecycle(LifecycleNode):
            def on_configure(self, state):
                del state
                events.append("lifecycle_configured")
                return TransitionCallbackReturn.SUCCESS

            def on_activate(self, state):
                del state
                events.append("lifecycle_activated")
                return TransitionCallbackReturn.SUCCESS

            def on_deactivate(self, state):
                del state
                events.append("lifecycle_deactivated")
                return TransitionCallbackReturn.SUCCESS

            def on_cleanup(self, state):
                del state
                events.append("lifecycle_cleaned_up")
                return TransitionCallbackReturn.SUCCESS

        def spin_until(predicate, timeout):
            deadline = time.time() + timeout
            while time.time() < deadline:
                executor.spin_once(timeout_sec=0.05)
                if predicate():
                    return True
            return predicate()

        def cancel_callback(goal_handle):
            events.append("cancel_callback")
            return CancelResponse.ACCEPT

        def navigate(goal_handle):
            request = goal_handle.request
            feedback = NavigateFleet.Feedback()
            feedback.current_pose = request.pose
            feedback.distance_remaining = 3.5
            feedback.estimated_time_remaining.sec = 4
            feedback.number_of_recoveries = 1
            goal_handle.publish_feedback(feedback)
            feedback_counts["navigation"] += 1
            result = NavigateFleet.Result()
            result.navigation_time.sec = 1
            if request.robot_id == "robot_nav_cancel":
                for _ in range(100):
                    if goal_handle.is_cancel_requested:
                        events.append("navigation_cancel_requested")
                        result.success = False
                        result.message = "navigation canceled"
                        goal_handle.canceled()
                        return result
                    time.sleep(0.03)
                result.message = "navigation cancel timeout"
                goal_handle.abort()
                return result
            events.append("navigation_succeeded")
            result.success = True
            result.message = "goal reached"
            goal_handle.succeed()
            return result

        def dispatch(goal_handle):
            request = goal_handle.request
            feedback = DispatchFleetTask.Feedback()
            feedback.state = "executing"
            feedback.progress = 0.5
            feedback.active_phase = request.phases[0] if request.phases else "none"
            feedback.completed_phases = 1
            goal_handle.publish_feedback(feedback)
            feedback_counts["task"] += 1
            result = DispatchFleetTask.Result()
            result.completion_time.sec = 42
            if request.task_id == "task_cancel":
                for _ in range(100):
                    if goal_handle.is_cancel_requested:
                        events.append("task_cancel_requested")
                        result.success = False
                        result.outcome = "task canceled"
                        goal_handle.canceled()
                        return result
                    time.sleep(0.03)
                result.outcome = "task cancel timeout"
                goal_handle.abort()
                return result
            events.append("task_succeeded")
            result.success = True
            result.outcome = "task completed"
            goal_handle.succeed()
            return result

        def navigate_upstream(goal_handle):
            request = goal_handle.request
            feedback = NavigateToPose.Feedback()
            feedback.current_pose = request.pose
            feedback.distance_remaining = 2.5
            feedback.estimated_time_remaining.sec = 3
            feedback.number_of_recoveries = 1
            goal_handle.publish_feedback(feedback)
            feedback_counts["navigation_upstream"] = (
                feedback_counts.get("navigation_upstream", 0) + 1)
            result = NavigateToPose.Result()
            if request.behavior_tree == "cancel":
                for _ in range(100):
                    if goal_handle.is_cancel_requested:
                        events.append("navigation_upstream_cancel_requested")
                        result.error_code = NavigateToPose.Result.NONE
                        result.error_msg = "navigation canceled"
                        goal_handle.canceled()
                        return result
                    time.sleep(0.03)
                result.error_msg = "navigation cancel timeout"
                goal_handle.abort()
                return result
            events.append("navigation_upstream_succeeded")
            result.error_code = NavigateToPose.Result.NONE
            result.error_msg = ""
            goal_handle.succeed()
            return result

        def submit_task(request, response):
            events.append("rmf_task_submitted")
            response.success = request.requester == "fleetqox"
            response.task_id = request.description.station.task_id or "rmf-task-001"
            response.message = "task accepted" if response.success else "invalid requester"
            return response

        def cancel_task(request, response):
            events.append("rmf_task_canceled")
            response.success = (
                request.requester == "fleetqox" and request.task_id == "rmf-task-001")
            response.message = "task canceled" if response.success else "task not found"
            return response

        summary = {"status": "pending"}
        try:
            rclpy.init()
            node = rclpy.create_node(
                "fleetqox_nav_rmf_action_server",
                enable_rosout=False,
                start_parameter_services=False)
            servers = [
                ActionServer(node, NavigateFleet, "/fleetqox/navigate", navigate,
                             cancel_callback=cancel_callback),
                ActionServer(node, DispatchFleetTask, "/fleetqox/dispatch_task", dispatch,
                             cancel_callback=cancel_callback),
                ActionServer(node, NavigateToPose, "/navigate_to_pose", navigate_upstream,
                             cancel_callback=cancel_callback),
            ]
            services = [
                node.create_service(SubmitTask, "/submit_task", submit_task),
                node.create_service(CancelTask, "/cancel_task", cancel_task),
            ]
            lifecycle_node = ManagedNavLifecycle("fleetqox_nav2_lifecycle")
            executor = MultiThreadedExecutor(num_threads=4)
            executor.add_node(node)
            executor.add_node(lifecycle_node)
            completed = spin_until(
                lambda: all(item in events for item in (
                    "navigation_succeeded", "navigation_cancel_requested",
                    "task_succeeded", "task_cancel_requested",
                    "navigation_upstream_succeeded",
                    "navigation_upstream_cancel_requested",
                    "lifecycle_configured", "lifecycle_activated",
                    "lifecycle_deactivated", "lifecycle_cleaned_up",
                    "rmf_task_submitted", "rmf_task_canceled")),
                25.0)
            spin_until(lambda: False, 1.0)
            summary = {
                "schema_version": "fleetrmw.nav2_rmf_action_server.v1",
                "status": "ok" if completed and min(feedback_counts.values()) >= 1 else "failed",
                "events": events,
                "feedback_counts": feedback_counts,
                "completed": completed,
            }
        except Exception as exc:
            summary = {"status": "exception", "exception": repr(exc), "traceback": traceback.format_exc()}
        finally:
            if executor is not None:
                executor.shutdown()
            for server in servers:
                server.destroy()
            if node is not None:
                for service in services:
                    node.destroy_service(service)
            if node is not None:
                node.destroy_node()
            if lifecycle_node is not None:
                lifecycle_node.destroy_node()
                lifecycle_node = None
                gc.collect()
            try:
                rclpy.shutdown()
            except Exception:
                pass
        print(json.dumps(summary, sort_keys=True))
        """
    )

    client_python = textwrap.dedent(
        """
        import json
        import time
        import traceback
        import rclpy
        from rclpy.action import ActionClient
        from rclpy.executors import MultiThreadedExecutor
        from fleetrmw_interfaces.action import NavigateFleet, DispatchFleetTask
        from nav2_msgs.action import NavigateToPose
        from lifecycle_msgs.msg import State
        from lifecycle_msgs.srv import GetState
        from nav2_msgs.srv import ManageLifecycleNodes
        from rmf_task_msgs.msg import TaskType
        from rmf_task_msgs.srv import SubmitTask, CancelTask

        summary = {"status": "pending", "feedback": []}
        executor = None
        node = None
        clients = []

        def spin_until(predicate, timeout):
            deadline = time.time() + timeout
            while time.time() < deadline:
                executor.spin_once(timeout_sec=0.05)
                if predicate():
                    return True
            return predicate()

        def feedback(label):
            def callback(message):
                del message
                summary["feedback"].append(label)
            return callback

        def complete_goal(client, goal, label, cancel=False):
            send = client.send_goal_async(goal, feedback_callback=feedback(label))
            if not spin_until(lambda: send.done(), 8.0):
                return {"send_done": False}
            handle = send.result()
            row = {"send_done": True, "accepted": bool(handle.accepted)}
            if cancel:
                spin_until(lambda: label in summary["feedback"], 4.0)
                cancel_future = handle.cancel_goal_async()
                row["cancel_done"] = spin_until(lambda: cancel_future.done(), 8.0)
                row["goals_canceling"] = (
                    len(cancel_future.result().goals_canceling) if row["cancel_done"] else 0)
            result_future = handle.get_result_async()
            row["result_done"] = spin_until(lambda: result_future.done(), 10.0)
            if row["result_done"]:
                wrapper = result_future.result()
                row["result_status"] = int(wrapper.status)
                row["result"] = wrapper.result
            return row

        def call_service(client, request, timeout=8.0):
            future = client.call_async(request)
            done = spin_until(lambda: future.done(), timeout)
            return future.result() if done else None

        def complete_goal_batch(client, goals, timeout=12.0):
            send_futures = [client.send_goal_async(goal) for goal in goals]
            sends_done = spin_until(lambda: all(item.done() for item in send_futures), timeout)
            handles = [item.result() for item in send_futures] if sends_done else []
            accepted = len(handles) == len(goals) and all(handle.accepted for handle in handles)
            result_futures = [handle.get_result_async() for handle in handles]
            results_done = accepted and spin_until(
                lambda: all(item.done() for item in result_futures), timeout)
            statuses = [int(item.result().status) for item in result_futures] if results_done else []
            return {
                "count": len(goals),
                "sends_done": sends_done,
                "accepted": accepted,
                "results_done": results_done,
                "statuses": statuses,
            }

        try:
            rclpy.init()
            node = rclpy.create_node(
                "fleetqox_nav_rmf_action_client",
                enable_rosout=False,
                start_parameter_services=False)
            nav = ActionClient(node, NavigateFleet, "/fleetqox/navigate")
            task = ActionClient(node, DispatchFleetTask, "/fleetqox/dispatch_task")
            nav_upstream = ActionClient(node, NavigateToPose, "/navigate_to_pose")
            submit = node.create_client(SubmitTask, "/submit_task")
            cancel_task_client = node.create_client(CancelTask, "/cancel_task")
            lifecycle_manager = node.create_client(
                ManageLifecycleNodes,
                "/lifecycle_manager_fleetqox/manage_nodes")
            lifecycle_state = node.create_client(
                GetState, "/fleetqox_nav2_lifecycle/get_state")
            clients = [
                nav, task, nav_upstream, submit, cancel_task_client,
                lifecycle_manager, lifecycle_state,
            ]
            executor = MultiThreadedExecutor(num_threads=4)
            executor.add_node(node)
            available = spin_until(
                lambda: (
                    nav.server_is_ready() and task.server_is_ready()
                    and nav_upstream.server_is_ready()
                    and submit.service_is_ready() and cancel_task_client.service_is_ready()
                    and lifecycle_manager.service_is_ready()
                    and lifecycle_state.service_is_ready()
                ),
                10.0)

            nav_goal = NavigateFleet.Goal()
            nav_goal.robot_id = "robot_0000"
            nav_goal.pose.header.frame_id = "map"
            nav_goal.pose.pose.position.x = 5.0
            nav_goal.pose.pose.orientation.w = 1.0
            nav_goal.behavior_tree = "navigate_to_pose"
            nav_success = complete_goal(nav, nav_goal, "nav_success")

            nav_cancel_goal = NavigateFleet.Goal()
            nav_cancel_goal.robot_id = "robot_nav_cancel"
            nav_cancel_goal.pose.header.frame_id = "map"
            nav_cancel_goal.pose.pose.position.x = 9.0
            nav_cancel_goal.pose.pose.orientation.w = 1.0
            nav_cancel = complete_goal(nav, nav_cancel_goal, "nav_cancel", cancel=True)

            task_goal = DispatchFleetTask.Goal()
            task_goal.task_id = "task_0001"
            task_goal.robot_id = "robot_0001"
            task_goal.category = "delivery"
            task_goal.priority = 7
            task_goal.phases = ["pickup", "navigate", "dropoff"]
            task_success = complete_goal(task, task_goal, "task_success")

            task_cancel_goal = DispatchFleetTask.Goal()
            task_cancel_goal.task_id = "task_cancel"
            task_cancel_goal.robot_id = "robot_0002"
            task_cancel_goal.category = "cleaning"
            task_cancel_goal.priority = 3
            task_cancel_goal.phases = ["navigate", "clean"]
            task_cancel = complete_goal(task, task_cancel_goal, "task_cancel", cancel=True)

            upstream_goal = NavigateToPose.Goal()
            upstream_goal.pose.header.frame_id = "map"
            upstream_goal.pose.pose.position.x = 4.0
            upstream_goal.pose.pose.orientation.w = 1.0
            upstream_goal.behavior_tree = "navigate"
            upstream_success = complete_goal(
                nav_upstream, upstream_goal, "nav_upstream_success")

            upstream_cancel_goal = NavigateToPose.Goal()
            upstream_cancel_goal.pose.header.frame_id = "map"
            upstream_cancel_goal.pose.pose.position.x = 8.0
            upstream_cancel_goal.pose.pose.orientation.w = 1.0
            upstream_cancel_goal.behavior_tree = "cancel"
            upstream_cancel = complete_goal(
                nav_upstream, upstream_cancel_goal, "nav_upstream_cancel", cancel=True)

            submit_request = SubmitTask.Request()
            submit_request.requester = "fleetqox"
            submit_request.description.task_type.type = TaskType.TYPE_STATION
            submit_request.description.station.task_id = "rmf-task-001"
            submit_request.description.station.robot_type = "fleet_robot"
            submit_request.description.station.place_name = "station_A"
            submit_response = call_service(submit, submit_request)

            concurrency = max(1, int(__import__("os").environ.get(
                "FLEETQOX_UPSTREAM_CONCURRENCY", "4")))
            batch_goals = []
            for index in range(concurrency):
                goal = NavigateToPose.Goal()
                goal.pose.header.frame_id = "map"
                goal.pose.pose.position.x = float(index + 10)
                goal.pose.pose.orientation.w = 1.0
                goal.behavior_tree = f"batch-{index}"
                batch_goals.append(goal)
            navigation_batch = complete_goal_batch(nav_upstream, batch_goals)

            batch_submit_requests = []
            for index in range(concurrency):
                request = SubmitTask.Request()
                request.requester = "fleetqox"
                request.description.task_type.type = TaskType.TYPE_STATION
                request.description.station.task_id = f"rmf-batch-{index:04d}"
                request.description.station.robot_type = "fleet_robot"
                request.description.station.place_name = f"station_{index:04d}"
                batch_submit_requests.append(request)
            batch_submit_futures = [
                submit.call_async(request) for request in batch_submit_requests
            ]
            batch_submit_done = spin_until(
                lambda: all(item.done() for item in batch_submit_futures), 12.0)
            batch_submit_responses = (
                [item.result() for item in batch_submit_futures]
                if batch_submit_done else []
            )

            startup_request = ManageLifecycleNodes.Request()
            startup_request.command = ManageLifecycleNodes.Request.STARTUP
            startup_response = call_service(lifecycle_manager, startup_request, timeout=12.0)
            active_state_response = call_service(lifecycle_state, GetState.Request())
            reset_request = ManageLifecycleNodes.Request()
            reset_request.command = ManageLifecycleNodes.Request.RESET
            reset_response = call_service(lifecycle_manager, reset_request, timeout=12.0)
            state_response = call_service(lifecycle_state, GetState.Request())
            lifecycle_ok = (
                startup_response is not None and startup_response.success
                and active_state_response is not None
                and active_state_response.current_state.id == State.PRIMARY_STATE_ACTIVE
                and reset_response is not None and reset_response.success
                and state_response is not None
                and state_response.current_state.id == State.PRIMARY_STATE_UNCONFIGURED
            )

            cancel_request = CancelTask.Request()
            cancel_request.requester = "fleetqox"
            cancel_request.task_id = (
                submit_response.task_id if submit_response is not None else ""
            )
            cancel_response = call_service(cancel_task_client, cancel_request)

            def result_ok(row, expected_status):
                return (
                    row.get("send_done") is True and row.get("accepted") is True and
                    row.get("result_done") is True and row.get("result_status") == expected_status)

            nav_ok = result_ok(nav_success, 4) and result_ok(nav_cancel, 5)
            task_ok = result_ok(task_success, 4) and result_ok(task_cancel, 5)
            nav_upstream_ok = (
                result_ok(upstream_success, 4)
                and result_ok(upstream_cancel, 5)
                and getattr(upstream_success.get("result"), "error_code", 1) == 0
            )
            rmf_upstream_ok = (
                submit_response is not None and submit_response.success
                and submit_response.task_id == "rmf-task-001"
                and cancel_response is not None and cancel_response.success
            )
            navigation_batch_ok = (
                navigation_batch["sends_done"] and navigation_batch["accepted"]
                and navigation_batch["results_done"]
                and navigation_batch["statuses"] == [4] * concurrency
            )
            rmf_batch_ok = (
                batch_submit_done and len(batch_submit_responses) == concurrency
                and all(response.success for response in batch_submit_responses)
                and [response.task_id for response in batch_submit_responses]
                == [f"rmf-batch-{index:04d}" for index in range(concurrency)]
            )
            summary.update({
                "status": "ok" if (
                    available and nav_ok and task_ok and nav_upstream_ok
                    and rmf_upstream_ok and navigation_batch_ok and rmf_batch_ok
                    and lifecycle_ok
                    and len(summary["feedback"]) >= 6
                ) else "failed",
                "available": available,
                "navigation": {
                    "success_status": nav_success.get("result_status"),
                    "success_message": getattr(nav_success.get("result"), "message", ""),
                    "cancel_status": nav_cancel.get("result_status"),
                    "cancel_goals": nav_cancel.get("goals_canceling", 0),
                },
                "task": {
                    "success_status": task_success.get("result_status"),
                    "success_outcome": getattr(task_success.get("result"), "outcome", ""),
                    "cancel_status": task_cancel.get("result_status"),
                    "cancel_goals": task_cancel.get("goals_canceling", 0),
                },
                "navigation_upstream": {
                    "success_status": upstream_success.get("result_status"),
                    "success_error_code": getattr(
                        upstream_success.get("result"), "error_code", -1),
                    "cancel_status": upstream_cancel.get("result_status"),
                    "cancel_goals": upstream_cancel.get("goals_canceling", 0),
                },
                "rmf_upstream": {
                    "submit_success": bool(
                        submit_response is not None and submit_response.success),
                    "task_id": (
                        submit_response.task_id if submit_response is not None else ""),
                    "cancel_success": bool(
                        cancel_response is not None and cancel_response.success),
                },
                "upstream_concurrency": concurrency,
                "navigation_batch": {**navigation_batch, "ok": navigation_batch_ok},
                "rmf_batch": {
                    "ok": rmf_batch_ok,
                    "count": concurrency,
                    "responses_done": len(batch_submit_responses),
                    "task_ids": [
                        response.task_id for response in batch_submit_responses
                    ],
                },
                "lifecycle": {
                    "ok": lifecycle_ok,
                    "manager_upstream": True,
                    "startup_success": bool(
                        startup_response is not None and startup_response.success),
                    "active_state_id": (
                        int(active_state_response.current_state.id)
                        if active_state_response is not None else -1),
                    "reset_success": bool(
                        reset_response is not None and reset_response.success),
                    "final_state_id": (
                        int(state_response.current_state.id)
                        if state_response is not None else -1),
                    "final_state_label": (
                        state_response.current_state.label
                        if state_response is not None else ""),
                },
            })
        except Exception as exc:
            summary.update({"status": "exception", "exception": repr(exc), "traceback": traceback.format_exc()})
        finally:
            if executor is not None:
                executor.shutdown()
            for client in clients:
                if hasattr(client, "destroy"):
                    client.destroy()
            if node is not None:
                node.destroy_node()
            try:
                rclpy.shutdown()
            except Exception:
                pass
        print(json.dumps(summary, sort_keys=True, default=str))
        """
    )

    try:
        docker_shell(
            "source /opt/ros/jazzy/setup.bash && "
            f"rm -rf {build_base} {install_base} {log_base} && "
            "colcon "
            f"--log-base {log_base} build --base-paths ros2_ws/src "
            "--packages-select fleetrmw_interfaces rmw_fleetqox_cpp "
            f"--build-base {build_base} --install-base {install_base} "
            "--cmake-args -DCMAKE_BUILD_TYPE=Release"
        )
        run(["docker", "network", "create", network])
        run([
            "docker", "run", "-d", "--name", router_name, "--network", network,
            "--entrypoint", "bash", "-v", f"{root}:/work", "-w", "/work", image, "-lc",
            "source /opt/ros/jazzy/setup.bash && "
            f"source {install_base}/setup.bash && "
            f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_udp_router_probe "
            "--bind 0.0.0.0:49700 --expected-frames 0 "
            f"--expected-service-frames {expected_service_frames} "
            "--expected-graph-advertisements 12 "
            "--post-satisfaction-ms 1000 --timeout-ms 35000",
        ])
        time.sleep(0.4)
        server_command = (
            "source /opt/ros/jazzy/setup.bash\n"
            f"source {install_base}/setup.bash\n"
            "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp\n"
            "export FLEETQOX_RMW_BIND=0.0.0.0:49701\n"
            f"export FLEETQOX_RMW_PEERS={router_name}:49700\n"
            "python3 - <<'PY'\n" + server_python + "\nPY\n"
        )
        run([
            "docker", "run", "-d", "--name", server_name, "--network", network,
            "--entrypoint", "bash", "-v", f"{root}:/work", "-w", "/work", image, "-lc",
            server_command,
        ])
        manager_command = (
            "source /opt/ros/jazzy/setup.bash\n"
            f"source {install_base}/setup.bash\n"
            "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp\n"
            "export FLEETQOX_RMW_BIND=0.0.0.0:49703\n"
            f"export FLEETQOX_RMW_PEERS={router_name}:49700\n"
            "ros2 run nav2_lifecycle_manager lifecycle_manager --ros-args "
            "-r __node:=lifecycle_manager_fleetqox "
            "-p autostart:=false -p bond_timeout:=0.0 "
            "-p node_names:=['fleetqox_nav2_lifecycle']\n"
        )
        run([
            "docker", "run", "-d", "--name", manager_name, "--network", network,
            "--entrypoint", "bash", "-v", f"{root}:/work", "-w", "/work", image, "-lc",
            manager_command,
        ])
        time.sleep(0.4)
        client = docker_shell(
            "source /opt/ros/jazzy/setup.bash\n"
            f"source {install_base}/setup.bash\n"
            "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp\n"
            f"export FLEETQOX_UPSTREAM_CONCURRENCY={upstream_concurrency}\n"
            "export FLEETQOX_RMW_BIND=0.0.0.0:49702\n"
            f"export FLEETQOX_RMW_PEERS={router_name}:49700\n"
            "python3 - <<'PY'\n" + client_python + "\nPY\n",
            "--network", network,
            check=False,
        )
        server_rc = int(run(["docker", "wait", server_name]).stdout.strip())
        router_rc = int(run(["docker", "wait", router_name]).stdout.strip())
        manager_state = run(
            ["docker", "inspect", "-f", "{{.State.Running}}", manager_name],
            check=False,
        ).stdout.strip()
        manager_running = manager_state == "true"
        server_log_result = run(["docker", "logs", server_name], check=False)
        server_logs = server_log_result.stdout + server_log_result.stderr
        manager_log_result = run(["docker", "logs", manager_name], check=False)
        manager_logs = manager_log_result.stdout + manager_log_result.stderr
        router_logs = run(["docker", "logs", router_name], check=False).stdout
        client_summary = parse_last_json(client.stdout)
        server_summary = parse_last_json(server_logs)
        router_summary = parse_last_json(router_logs)
        nav_ok = (
            client_summary.get("navigation", {}).get("success_status") == 4
            and client_summary.get("navigation", {}).get("cancel_status") == 5
        )
        task_ok = (
            client_summary.get("task", {}).get("success_status") == 4
            and client_summary.get("task", {}).get("cancel_status") == 5
        )
        nav_upstream_ok = (
            client_summary.get("navigation_upstream", {}).get("success_status") == 4
            and client_summary.get("navigation_upstream", {}).get("cancel_status") == 5
            and client_summary.get("navigation_upstream", {}).get("success_error_code") == 0
        )
        rmf_upstream_ok = (
            client_summary.get("rmf_upstream", {}).get("submit_success") is True
            and client_summary.get("rmf_upstream", {}).get("cancel_success") is True
            and client_summary.get("rmf_upstream", {}).get("task_id") == "rmf-task-001"
        )
        navigation_batch_ok = (
            client_summary.get("navigation_batch", {}).get("ok") is True
            and client_summary.get("navigation_batch", {}).get("count")
            == upstream_concurrency
        )
        rmf_batch_ok = (
            client_summary.get("rmf_batch", {}).get("ok") is True
            and client_summary.get("rmf_batch", {}).get("count")
            == upstream_concurrency
        )
        lifecycle_ok = (
            client_summary.get("lifecycle", {}).get("ok") is True
            and client_summary.get("lifecycle", {}).get("manager_upstream") is True
            and manager_running
        )
        status = (
            client.returncode == 0 and server_rc == 0 and router_rc == 0
            and client_summary.get("status") == "ok"
            and server_summary.get("status") == "ok"
            and router_summary.get("status") == "ok"
            and int(router_summary.get("service_frames", 0)) >= expected_service_frames
            and int(router_summary.get("service_forwarded", 0)) >= expected_service_frames
            and int(router_summary.get("graph_services", 0)) >= 11
            and int(router_summary.get("graph_clients", 0)) >= 9
            and nav_ok and task_ok and nav_upstream_ok and rmf_upstream_ok
            and navigation_batch_ok and rmf_batch_ok and lifecycle_ok
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if status else "failed",
            "nav2_compatible": nav_ok,
            "rmf_compatible": task_ok,
            "nav2_upstream": nav_upstream_ok,
            "rmf_upstream": rmf_upstream_ok,
            "upstream_concurrency": upstream_concurrency,
            "expected_service_frames": expected_service_frames,
            "navigation_batch": navigation_batch_ok,
            "rmf_batch": rmf_batch_ok,
            "lifecycle_transport": lifecycle_ok,
            "nav2_lifecycle_manager_upstream": lifecycle_ok,
            "manager_running_after_workload": manager_running,
            "client_returncode": client.returncode,
            "server_returncode": server_rc,
            "router_returncode": router_rc,
            "client": client_summary,
            "server": server_summary,
            "router": router_summary,
            "client_stdout": client.stdout,
            "client_stderr": client.stderr,
            "server_logs": server_logs,
            "manager_logs": manager_logs,
            "router_logs": router_logs,
        }
    except subprocess.CalledProcessError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "returncode": exc.returncode,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
    finally:
        run(["docker", "rm", "-f", router_name, server_name, manager_name], check=False)
        run(["docker", "network", "rm", network], check=False)
        docker_shell(f"rm -rf {build_base} {install_base} {log_base}", check=False)


if __name__ == "__main__":
    raise SystemExit(main())
