"""Run Nav2/RMF-compatible action semantics through the FleetRMW router."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_router_service_call_probe import parse_last_json
from scripts.run_rmw_docker_quic_mtls_probe import certificate_command
from scripts.run_rmw_docker_quic_stateful_gateway_probe import (
    SERVICE_SCHEMA_VERSION as QUIC_SERVICE_SCHEMA_VERSION,
    json_rows,
    wait_service_ready,
)


SCHEMA_VERSION = "fleetrmw.rmw_router_nav2_rmf_action_workload.v6"
DEFAULT_IMAGE = "localhost/fleetrmw/rmw-netem:jazzy"


def task_outcomes_ok(
    client_summary: dict[str, Any],
    *,
    expected_gateway_submission: bool | None = False,
) -> bool:
    """Validate the three terminal-result mappings emitted by the workload."""

    outcomes = client_summary.get("application_outcomes")
    if not isinstance(outcomes, list) or len(outcomes) != 3:
        return False
    expected = (
        (1, "nav2", "succeeded", True, True),
        (2, "nav2", "canceled", True, False),
        (3, "rmf", "succeeded", True, True),
    )
    for document, row in zip(outcomes, expected):
        sequence, task_kind, terminal_status, delivered, task_succeeded = row
        if not isinstance(document, dict) or (
            document.get("schema_version")
            != "fleetrmw.quic_gateway_application_outcome.v1"
            or document.get("domain_id") != 42
            or document.get("topic") != "/fleetqox/nav2_rmf_tasks"
            or document.get("publisher_id") != "nav2-rmf-workload-client"
            or document.get("source_sequence_number") != sequence
            or document.get("task_kind") != task_kind
            or document.get("terminal_status") != terminal_status
            or document.get("delivered") is not delivered
            or document.get("task_succeeded") is not task_succeeded
            or document.get("deadline_met") is not True
        ):
            return False
    return expected_gateway_submission is None or (
        client_summary.get("task_outcome_gateway_submission_performed")
        is expected_gateway_submission
    )


def live_task_outcome_submission_ok(client_summary: dict[str, Any]) -> bool:
    """Validate one-process live ROS result submission and H3 session reuse."""

    submission = client_summary.get("task_outcome_gateway_submission")
    return (
        isinstance(submission, dict)
        and submission.get("schema_version")
        == "fleetrmw.live_task_outcome_client.v1"
        and submission.get("status") == "ok"
        and submission.get("process_id") == client_summary.get("process_id")
        and submission.get("connections_created") == 1
        and submission.get("handshakes_completed") == 1
        and submission.get("streams_opened") == 6
        and submission.get("connection_reuse_count") == 5
        and submission.get("seed_frames_sent") == 3
        and submission.get("task_outcomes_submitted") == 3
        and submission.get("task_outcome_submission_session_reuse_claim") is True
        and submission.get("mutual_tls_required") is True
        and submission.get("production_readiness") is False
        and client_summary.get("rclpy_context_active_during_gateway_submission")
        is True
        and client_summary.get("ros_node_alive_during_gateway_submission") is True
        and client_summary.get("task_outcome_gateway_submission_performed") is True
    )


def live_task_outcome_service_ok(service: dict[str, Any]) -> bool:
    """Validate the gateway state produced by the same-process workload."""

    metrics = service.get("metrics", {})
    admission = metrics.get("admission", {})
    transport = service.get("transport_metrics", {})
    return (
        service.get("schema_version") == QUIC_SERVICE_SCHEMA_VERSION
        and service.get("status") == "stopped"
        and service.get("clean_teardown") is True
        and service.get("client_certificate_required") is True
        and service.get("publisher_identity_binding") is True
        and service.get("publisher_identity_source") == "uri_san"
        and metrics.get("requests_total") == 6
        and metrics.get("post_requests") == 3
        and metrics.get("application_outcome_requests") == 3
        and metrics.get("application_outcome_updates") == 3
        and metrics.get("application_outcome_unknown_frames") == 0
        and metrics.get("invalid_application_outcomes") == 0
        and metrics.get("application_task_outcome_updates") == 3
        and metrics.get("application_task_outcome_failures") == 1
        and metrics.get("accepted_frames") == 3
        and metrics.get("invalid_frames") == 0
        and metrics.get("retained_frames") == 3
        and metrics.get("application_outcome_key_count") == 3
        and admission.get("accepted_total") == 3
        and admission.get("application_outcome_qoe_debt_updates") == 3
        and admission.get("application_task_outcome_updates") == 3
        and admission.get("application_task_outcome_failures") == 1
        and transport.get("connections_created") == 1
        and transport.get("h3_sessions_negotiated") == 1
        and transport.get("client_certificates_accepted") == 1
        and transport.get("publisher_identity_authorization_rejected") == 0
        and transport.get("application_outcome_identity_authorization_rejected")
        == 0
        and transport.get("malformed_h3_requests_rejected") == 0
        and transport.get("mtls_private_adapter_installs") == 1
    )


def live_task_outcome_policy() -> dict[str, Any]:
    return {
        "schema_version": "fleetrmw.quic_gateway_admission_policy.v1",
        "default_action": "deny",
        "application_outcome_qoe_debt": {"enabled": True, "ewma_alpha": 1.0},
        "rules": [
            {
                "domain_id": 42,
                "topic": "/fleetqox/nav2_rmf_tasks",
                "traffic_class": "control",
                "max_accepted_frames": 3,
                "allowed_publishers": ["nav2-rmf-workload-client"],
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--upstream-concurrency", type=int, default=4)
    parser.add_argument(
        "--goal-batch-size",
        type=int,
        default=0,
        help=(
            "Number of upstream NavigateToPose goals sent concurrently per batch. "
            "0 keeps the historical single-batch behavior."
        ),
    )
    parser.add_argument(
        "--goal-batch-timeout-s",
        type=float,
        default=0.0,
        help="Per-goal-batch action timeout. 0 derives it from the workload size.",
    )
    parser.add_argument(
        "--goal-send-pacing-ms",
        type=float,
        default=0.0,
        help=(
            "Pacing between send_goal_async calls inside each batch. "
            "Zero selects 0.5 ms automatically at concurrency 4096 or higher."
        ),
    )
    parser.add_argument(
        "--goal-batch-delay-ms",
        type=float,
        default=0.0,
        help="Optional executor-spun delay between goal batches.",
    )
    parser.add_argument(
        "--live-task-outcome-gateway",
        action="store_true",
        help=(
            "Submit the actual Nav2/RMF terminal results from the still-live ROS "
            "client process to a netem-impaired mTLS/HTTP/3 gateway."
        ),
    )
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
        goal_batch_size=max(args.goal_batch_size, 0),
        goal_batch_timeout_s=args.goal_batch_timeout_s,
        goal_send_pacing_ms=max(args.goal_send_pacing_ms, 0.0),
        goal_batch_delay_ms=max(args.goal_batch_delay_ms, 0.0),
        live_task_outcome_gateway=args.live_task_outcome_gateway,
    )
    path = root / args.summary_json
    path.parent.mkdir(parents=True, exist_ok=True)
    output_path = path
    if summary.get("status") == "docker_unavailable" and path.exists():
        output_path = path.with_name(f"{path.stem}_docker_unavailable{path.suffix}")
        summary["preserved_existing_summary"] = str(path)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-nav2-rmf-action-workload")
        print(f"  status: {summary['status']}")
        print(f"  nav2_compatible: {summary.get('nav2_compatible')}")
        print(f"  rmf_compatible: {summary.get('rmf_compatible')}")
        print(f"  service_frames: {summary.get('router', {}).get('service_frames')}")
    return 0 if summary["status"] == "ok" else 1


def run_probe(
    *,
    root: Path,
    image: str,
    upstream_concurrency: int = 4,
    goal_batch_size: int = 0,
    goal_batch_timeout_s: float = 0.0,
    goal_send_pacing_ms: float = 0.0,
    goal_batch_delay_ms: float = 0.0,
    live_task_outcome_gateway: bool = False,
) -> dict[str, Any]:
    if upstream_concurrency <= 0:
        raise ValueError("upstream_concurrency must be positive")
    suffix = str(os.getpid())
    network = f"fleetrmw-nav-rmf-net-{suffix}"
    router_name = f"fleetrmw-nav-rmf-router-{suffix}"
    server_name = f"fleetrmw-nav-rmf-server-{suffix}"
    manager_name = f"fleetrmw-nav-rmf-lifecycle-manager-{suffix}"
    gateway_name = f"fleetrmw-nav-rmf-task-gateway-{suffix}"
    gateway_alias = "fleetqox-mtls-gateway"
    gateway_port = 4512
    gateway_temp_root = root / f".tmp_fleetrmw_nav_rmf_live_outcome_{suffix}"
    gateway_certs = gateway_temp_root / "certs"
    gateway_policy = gateway_temp_root / "admission-policy.json"
    gateway_service_qlogs = gateway_temp_root / "service-qlogs"
    gateway_client_qlogs = gateway_temp_root / "client-qlogs"
    build_base = "/work/.tmp_fleetrmw_nav_rmf_build"
    install_base = "/work/.tmp_fleetrmw_nav_rmf_install"
    log_base = "/work/.tmp_fleetrmw_nav_rmf_log"
    expected_service_frames = 58 + upstream_concurrency * 6
    requested_goal_send_pacing_ms = goal_send_pacing_ms
    if goal_send_pacing_ms == 0.0 and upstream_concurrency >= 4096:
        goal_send_pacing_ms = 0.5
    if upstream_concurrency <= 2048:
        batch_timeout_s = max(12, min(120, 12 + upstream_concurrency // 8))
    else:
        batch_timeout_s = max(12, min(720, 12 + upstream_concurrency // 8))
    effective_goal_batch_size = (
        upstream_concurrency
        if goal_batch_size <= 0
        else max(1, min(goal_batch_size, upstream_concurrency))
    )
    goal_batch_count = (
        upstream_concurrency + effective_goal_batch_size - 1
    ) // effective_goal_batch_size
    derived_goal_batch_timeout_s = (
        batch_timeout_s if goal_batch_count == 1
        else max(12, min(batch_timeout_s, 12 + effective_goal_batch_size // 8))
    )
    if goal_batch_timeout_s <= 0:
        goal_batch_timeout_s = derived_goal_batch_timeout_s
    workload_timeout_s = (
        batch_timeout_s * 2 if goal_batch_count == 1
        else goal_batch_timeout_s * goal_batch_count + batch_timeout_s
    )
    server_timeout_s = max(30, min(1800, workload_timeout_s + 120))
    executor_threads = max(4, min(16, 4 + upstream_concurrency // 512))
    result_window_size = max(64, min(512, upstream_concurrency // 4))
    goal_recreate_client_per_batch = False
    udp_socket_buffer_bytes = 16 * 1024 * 1024
    udp_send_pacing_us = 250 if upstream_concurrency >= 4096 else 0
    service_request_repeats = (
        3
        if upstream_concurrency >= 4096
        else 2
        if live_task_outcome_gateway
        else 0
    )
    service_response_repeats = (
        3
        if upstream_concurrency >= 4096
        else 2
        if live_task_outcome_gateway
        else 0
    )
    service_request_repeat_interval_ms = 1
    service_response_repeat_interval_ms = 1
    router_post_satisfaction_ms = 30000 if upstream_concurrency >= 4096 else 1000
    router_expected_service_frames = (
        0 if upstream_concurrency >= 4096 else expected_service_frames
    )
    router_timeout_ms = max(35000, int((80 + workload_timeout_s) * 1000))

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

    try:
        docker_check = run(["docker", "version", "--format", "{{.Server.Version}}"], check=False)
    except FileNotFoundError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "docker_unavailable",
            "docker_available": False,
            "error": repr(exc),
        }
    if docker_check.returncode != 0:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "docker_unavailable",
            "docker_available": False,
            "returncode": docker_check.returncode,
            "stdout": docker_check.stdout,
            "stderr": docker_check.stderr,
        }

    server_python = textwrap.dedent(
        """
        import json
        import gc
        import os
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
            executor_threads = int(os.environ.get("FLEETQOX_EXECUTOR_THREADS", "4"))
            executor = MultiThreadedExecutor(num_threads=executor_threads)
            executor.add_node(node)
            executor.add_node(lifecycle_node)
            server_timeout = float(os.environ.get("FLEETQOX_SERVER_TIMEOUT_S", "25"))
            completed = spin_until(
                lambda: all(item in events for item in (
                    "navigation_succeeded", "navigation_cancel_requested",
                    "task_succeeded", "task_cancel_requested",
                    "navigation_upstream_succeeded",
                    "navigation_upstream_cancel_requested",
                    "lifecycle_configured", "lifecycle_activated",
                    "lifecycle_deactivated", "lifecycle_cleaned_up",
                    "rmf_task_submitted", "rmf_task_canceled")),
                server_timeout)
            spin_until(lambda: False, 1.0)
            summary = {
                "schema_version": "fleetrmw.nav2_rmf_action_server.v1",
                "status": "ok" if completed and min(feedback_counts.values()) >= 1 else "failed",
                "events": events,
                "feedback_counts": feedback_counts,
                "completed": completed,
                "server_timeout_s": server_timeout,
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
        import os
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
        from fleetqox.task_outcome import (
            TaskOutcomeCorrelation,
            nav2_application_outcome,
            rmf_application_outcome,
        )
        from fleetqox.live_task_outcome_client import submit_live_task_outcomes

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
            started = time.monotonic()
            send = client.send_goal_async(goal, feedback_callback=feedback(label))
            if not spin_until(lambda: send.done(), 8.0):
                return {
                    "send_done": False,
                    "observed_latency_ms": (time.monotonic() - started) * 1000.0,
                }
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
            row["observed_latency_ms"] = (time.monotonic() - started) * 1000.0
            return row

        def call_service(client, request, timeout=8.0):
            future = client.call_async(request)
            done = spin_until(lambda: future.done(), timeout)
            return future.result() if done else None

        def complete_goal_batch(client, goals, timeout=12.0):
            send_pacing_s = max(0.0, float(__import__("os").environ.get(
                "FLEETQOX_GOAL_SEND_PACING_MS", "0"))) / 1000.0
            send_futures = []
            for goal in goals:
                send_futures.append(client.send_goal_async(goal))
                if send_pacing_s > 0.0:
                    deadline = time.time() + send_pacing_s
                    while time.time() < deadline:
                        executor.spin_once(timeout_sec=min(0.01, max(0.0, deadline - time.time())))
            processed_sends = set()
            handles = []
            send_errors = []
            result_window_size = max(1, int(__import__("os").environ.get(
                "FLEETQOX_RESULT_WINDOW_SIZE", "512")))
            deadline = time.time() + timeout
            while time.time() < deadline:
                executor.spin_once(timeout_sec=0.05)
                for index, item in enumerate(send_futures):
                    if index in processed_sends or not item.done():
                        continue
                    processed_sends.add(index)
                    try:
                        handle = item.result()
                    except Exception as exc:
                        send_errors.append(repr(exc))
                        continue
                    handles.append(handle)
                if len(processed_sends) == len(send_futures):
                    break
            for index, item in enumerate(send_futures):
                if index in processed_sends or not item.done():
                    continue
                processed_sends.add(index)
                try:
                    handle = item.result()
                except Exception as exc:
                    send_errors.append(repr(exc))
                    continue
                handles.append(handle)
            sends_done = len(processed_sends) == len(send_futures)
            accepted = len(handles) == len(goals) and all(handle.accepted for handle in handles)
            statuses = []
            result_future_count = 0
            result_done_count = 0
            results_done = accepted
            result_window_count = (
                (len(handles) + result_window_size - 1) // result_window_size
                if accepted else 0
            )
            result_window_timeout = (
                max(8.0, timeout / max(1, result_window_count))
                if accepted else 0.0
            )
            if accepted:
                for offset in range(0, len(handles), result_window_size):
                    result_futures = [
                        handle.get_result_async()
                        for handle in handles[offset:offset + result_window_size]
                    ]
                    result_future_count += len(result_futures)
                    chunk_done = spin_until(
                        lambda: all(item.done() for item in result_futures),
                        result_window_timeout)
                    result_done_count += sum(1 for item in result_futures if item.done())
                    if not chunk_done:
                        results_done = False
                        break
                    statuses.extend(int(item.result().status) for item in result_futures)
            ok = (
                sends_done and accepted and results_done
                and statuses == [4] * len(goals)
            )
            return {
                "count": len(goals),
                "sends_done": sends_done,
                "send_done_count": len(processed_sends),
                "send_error_count": len(send_errors),
                "accepted_count": sum(1 for handle in handles if handle.accepted),
                "accepted": accepted,
                "results_done": results_done,
                "result_window_size": result_window_size,
                "result_window_count": result_window_count,
                "result_window_timeout_s": result_window_timeout,
                "result_future_count": result_future_count,
                "result_done_count": result_done_count,
                "ok": ok,
                "statuses": statuses,
            }

        def failed_goal_batch(count, reason):
            return {
                "count": count,
                "sends_done": False,
                "send_done_count": 0,
                "send_error_count": 1,
                "accepted_count": 0,
                "accepted": False,
                "results_done": False,
                "result_window_size": 0,
                "result_window_count": 0,
                "result_window_timeout_s": 0.0,
                "result_future_count": 0,
                "result_done_count": 0,
                "ok": False,
                "statuses": [],
                "error": reason,
            }

        def complete_goal_batches(
            client, goals, batch_size, timeout=12.0, client_factory=None):
            batch_size = max(1, int(batch_size))
            batch_delay_s = max(0.0, float(__import__("os").environ.get(
                "FLEETQOX_GOAL_BATCH_DELAY_MS", "0"))) / 1000.0
            chunks = []
            statuses = []
            send_done_count = 0
            send_error_count = 0
            accepted_count = 0
            result_future_count = 0
            result_done_count = 0
            recreated_client_batches = 0
            for offset in range(0, len(goals), batch_size):
                active_client = client
                owns_client = False
                if client_factory is not None:
                    active_client = client_factory()
                    owns_client = True
                    recreated_client_batches += 1
                    if not spin_until(lambda: active_client.server_is_ready(), 10.0):
                        chunk = failed_goal_batch(
                            len(goals[offset:offset + batch_size]),
                            "batch_action_client_not_ready")
                        chunks.append(chunk)
                        break
                try:
                    chunk = complete_goal_batch(
                        active_client,
                        goals[offset:offset + batch_size],
                        timeout=timeout)
                finally:
                    if owns_client and hasattr(active_client, "destroy"):
                        active_client.destroy()
                chunks.append(chunk)
                send_done_count += int(chunk.get("send_done_count", 0))
                send_error_count += int(chunk.get("send_error_count", 0))
                accepted_count += int(chunk.get("accepted_count", 0))
                result_future_count += int(chunk.get("result_future_count", 0))
                result_done_count += int(chunk.get("result_done_count", 0))
                statuses.extend(chunk.get("statuses", []))
                if not chunk.get("ok", False):
                    break
                if batch_delay_s > 0.0 and offset + batch_size < len(goals):
                    deadline = time.time() + batch_delay_s
                    while time.time() < deadline:
                        executor.spin_once(timeout_sec=min(0.05, max(0.0, deadline - time.time())))
            sends_done = send_done_count == len(goals)
            accepted = accepted_count == len(goals)
            results_done = result_done_count == len(goals)
            return {
                "count": len(goals),
                "goal_batch_size": batch_size,
                "goal_batch_count": (len(goals) + batch_size - 1) // batch_size,
                "goal_batch_delay_ms": batch_delay_s * 1000.0,
                "completed_goal_batch_count": len(chunks),
                "recreated_client_batches": recreated_client_batches,
                "sends_done": sends_done,
                "send_done_count": send_done_count,
                "send_error_count": send_error_count,
                "accepted_count": accepted_count,
                "accepted": accepted,
                "results_done": results_done,
                "result_future_count": result_future_count,
                "result_done_count": result_done_count,
                "statuses": statuses,
                "chunks": chunks,
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
            executor_threads = int(__import__("os").environ.get(
                "FLEETQOX_EXECUTOR_THREADS", "4"))
            executor = MultiThreadedExecutor(num_threads=executor_threads)
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
            submit_started = time.monotonic()
            submit_response = call_service(submit, submit_request)
            submit_latency_ms = (time.monotonic() - submit_started) * 1000.0

            concurrency = max(1, int(__import__("os").environ.get(
                "FLEETQOX_UPSTREAM_CONCURRENCY", "4")))
            batch_timeout = float(__import__("os").environ.get(
                "FLEETQOX_BATCH_TIMEOUT_S", "12"))
            goal_batch_size = max(1, int(__import__("os").environ.get(
                "FLEETQOX_GOAL_BATCH_SIZE", str(concurrency))))
            goal_batch_timeout = float(__import__("os").environ.get(
                "FLEETQOX_GOAL_BATCH_TIMEOUT_S", str(batch_timeout)))
            goal_send_pacing_ms = float(__import__("os").environ.get(
                "FLEETQOX_GOAL_SEND_PACING_MS", "0"))
            goal_batch_delay_ms = float(__import__("os").environ.get(
                "FLEETQOX_GOAL_BATCH_DELAY_MS", "0"))
            result_window_size = max(1, int(__import__("os").environ.get(
                "FLEETQOX_RESULT_WINDOW_SIZE", "512")))
            batch_goals = []
            for index in range(concurrency):
                goal = NavigateToPose.Goal()
                goal.pose.header.frame_id = "map"
                goal.pose.pose.position.x = float(index + 10)
                goal.pose.pose.orientation.w = 1.0
                goal.behavior_tree = f"batch-{index}"
                batch_goals.append(goal)
            goal_recreate_client_per_batch = (
                __import__("os").environ.get(
                    "FLEETQOX_GOAL_RECREATE_CLIENT_PER_BATCH", "0") == "1"
            )
            batch_client_factory = (
                (lambda: ActionClient(node, NavigateToPose, "/navigate_to_pose"))
                if goal_recreate_client_per_batch else None
            )
            navigation_batch = complete_goal_batches(
                nav_upstream, batch_goals,
                batch_size=goal_batch_size,
                timeout=goal_batch_timeout,
                client_factory=batch_client_factory)

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
                lambda: all(item.done() for item in batch_submit_futures), batch_timeout)
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

            task_outcomes = []
            task_outcome_mapping_error = ""
            try:
                task_outcomes = [
                    nav2_application_outcome(
                        TaskOutcomeCorrelation(
                            42,
                            "/fleetqox/nav2_rmf_tasks",
                            "nav2-rmf-workload-client",
                            1,
                        ),
                        goal_status=upstream_success.get("result_status"),
                        observed_latency_ms=upstream_success.get(
                            "observed_latency_ms", 10000.0),
                        deadline_ms=10000.0,
                    ),
                    nav2_application_outcome(
                        TaskOutcomeCorrelation(
                            42,
                            "/fleetqox/nav2_rmf_tasks",
                            "nav2-rmf-workload-client",
                            2,
                        ),
                        goal_status=upstream_cancel.get("result_status"),
                        observed_latency_ms=upstream_cancel.get(
                            "observed_latency_ms", 10000.0),
                        deadline_ms=10000.0,
                    ),
                    rmf_application_outcome(
                        TaskOutcomeCorrelation(
                            42,
                            "/fleetqox/nav2_rmf_tasks",
                            "nav2-rmf-workload-client",
                            3,
                        ),
                        response_received=submit_response is not None,
                        response_success=bool(
                            submit_response is not None and submit_response.success),
                        observed_latency_ms=submit_latency_ms,
                        deadline_ms=10000.0,
                    ),
                ]
            except ValueError as exc:
                task_outcome_mapping_error = repr(exc)
            task_outcome_mapping_ok = (
                len(task_outcomes) == 3
                and [row["terminal_status"] for row in task_outcomes]
                == ["succeeded", "canceled", "succeeded"]
                and [row["delivered"] for row in task_outcomes]
                == [True, True, True]
                and [row["task_succeeded"] for row in task_outcomes]
                == [True, False, True]
                and all(row["deadline_met"] for row in task_outcomes)
            )
            gateway_submission_requested = (
                os.environ.get("FLEETQOX_LIVE_TASK_OUTCOME_GATEWAY", "0") == "1"
            )
            task_outcome_gateway_submission = {
                "schema_version": "fleetrmw.live_task_outcome_client.v1",
                "status": "disabled",
                "production_readiness": False,
            }
            gateway_submission_error = ""
            rclpy_context_active_during_gateway_submission = False
            ros_node_alive_during_gateway_submission = False
            if gateway_submission_requested and task_outcome_mapping_ok:
                rclpy_context_active_during_gateway_submission = rclpy.ok()
                ros_node_alive_during_gateway_submission = node is not None
                try:
                    task_outcome_gateway_submission = submit_live_task_outcomes(
                        host=os.environ["FLEETQOX_TASK_OUTCOME_GATEWAY_HOST"],
                        port=int(os.environ["FLEETQOX_TASK_OUTCOME_GATEWAY_PORT"]),
                        ca_file=os.environ["FLEETQOX_TASK_OUTCOME_CA_FILE"],
                        client_certificate=os.environ[
                            "FLEETQOX_TASK_OUTCOME_CLIENT_CERT_FILE"
                        ],
                        client_private_key=os.environ[
                            "FLEETQOX_TASK_OUTCOME_CLIENT_KEY_FILE"
                        ],
                        outcomes=task_outcomes,
                        timeout_s=float(os.environ.get(
                            "FLEETQOX_TASK_OUTCOME_TIMEOUT_S", "10"
                        )),
                        qlog_dir=os.environ.get(
                            "FLEETQOX_TASK_OUTCOME_QLOG_DIR"
                        ),
                    )
                except Exception as exc:
                    gateway_submission_error = repr(exc)
                    task_outcome_gateway_submission = {
                        "schema_version": "fleetrmw.live_task_outcome_client.v1",
                        "status": "exception",
                        "exception": repr(exc),
                        "process_id": os.getpid(),
                        "production_readiness": False,
                    }
            gateway_submission_performed = (
                gateway_submission_requested
                and task_outcome_gateway_submission.get("status") == "ok"
                and task_outcome_gateway_submission.get("process_id") == os.getpid()
                and rclpy_context_active_during_gateway_submission
                and ros_node_alive_during_gateway_submission
            )

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
                    and lifecycle_ok and task_outcome_mapping_ok
                    and (
                        not gateway_submission_requested
                        or gateway_submission_performed
                    )
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
                "application_outcomes": task_outcomes,
                "task_outcome_mapping_ok": task_outcome_mapping_ok,
                "task_outcome_mapping_error": task_outcome_mapping_error,
                "task_outcome_gateway_submission_requested": (
                    gateway_submission_requested
                ),
                "task_outcome_gateway_submission_performed": (
                    gateway_submission_performed
                ),
                "task_outcome_gateway_submission": (
                    task_outcome_gateway_submission
                ),
                "task_outcome_gateway_submission_error": (
                    gateway_submission_error
                ),
                "process_id": os.getpid(),
                "rclpy_context_active_during_gateway_submission": (
                    rclpy_context_active_during_gateway_submission
                ),
                "ros_node_alive_during_gateway_submission": (
                    ros_node_alive_during_gateway_submission
                ),
                "upstream_concurrency": concurrency,
                "batch_timeout_s": batch_timeout,
                "goal_batch_size": goal_batch_size,
                "goal_batch_timeout_s": goal_batch_timeout,
                "goal_send_pacing_ms": goal_send_pacing_ms,
                "goal_batch_delay_ms": goal_batch_delay_ms,
                "goal_recreate_client_per_batch": goal_recreate_client_per_batch,
                "executor_threads": executor_threads,
                "result_window_size": result_window_size,
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

    gateway_ready = not live_task_outcome_gateway
    gateway_exit_code = 0 if not live_task_outcome_gateway else -1
    gateway_service_logs = ""
    gateway_service_summary: dict[str, Any] = {}
    gateway_qlog_file_count = 0
    gateway_qlog_total_bytes = 0
    client_netem_prefix = ""
    live_gateway_environment = ""
    client_extra_docker_args: tuple[str, ...] = ()
    if live_task_outcome_gateway:
        client_netem_prefix = (
            "tc qdisc replace dev eth0 root netem delay 9ms 2ms loss 0.2%\n"
            "tc qdisc show dev eth0\n"
        )
        live_gateway_environment = (
            "export FLEETQOX_LIVE_TASK_OUTCOME_GATEWAY=1\n"
            f"export FLEETQOX_TASK_OUTCOME_GATEWAY_HOST={gateway_alias}\n"
            f"export FLEETQOX_TASK_OUTCOME_GATEWAY_PORT={gateway_port}\n"
            f"export FLEETQOX_TASK_OUTCOME_CA_FILE=/work/"
            f"{(gateway_certs / 'server-ca.crt').relative_to(root)}\n"
            f"export FLEETQOX_TASK_OUTCOME_CLIENT_CERT_FILE=/work/"
            f"{(gateway_certs / 'client.crt').relative_to(root)}\n"
            f"export FLEETQOX_TASK_OUTCOME_CLIENT_KEY_FILE=/work/"
            f"{(gateway_certs / 'client.key').relative_to(root)}\n"
            f"export FLEETQOX_TASK_OUTCOME_QLOG_DIR=/work/"
            f"{gateway_client_qlogs.relative_to(root)}\n"
            "export FLEETQOX_TASK_OUTCOME_TIMEOUT_S=10\n"
        )
        client_extra_docker_args = ("--cap-add", "NET_ADMIN")

    try:
        if live_task_outcome_gateway:
            gateway_certs.mkdir(parents=True, exist_ok=True)
            gateway_service_qlogs.mkdir(parents=True, exist_ok=True)
            gateway_client_qlogs.mkdir(parents=True, exist_ok=True)
            gateway_policy.write_text(
                json.dumps(live_task_outcome_policy(), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            docker_shell(
                certificate_command(gateway_certs, root).replace(
                    "mtls-publisher", "nav2-rmf-workload-client"
                )
            )
        docker_shell(
            "source /opt/ros/jazzy/setup.bash && "
            f"rm -rf {build_base} {install_base} {log_base} && "
            "export CMAKE_BUILD_PARALLEL_LEVEL=2 && "
            f"colcon --log-base {log_base} build --executor sequential "
            "--base-paths ros2_ws/src "
            "--packages-select fleetrmw_interfaces rmw_fleetqox_cpp "
            f"--build-base {build_base} --install-base {install_base} "
            "--cmake-args -DCMAKE_BUILD_TYPE=Release"
        )
        run(["docker", "network", "create", network])
        if live_task_outcome_gateway:
            gateway_service_command = (
                "tc qdisc replace dev eth0 root netem "
                "delay 11ms 2ms loss 0.2% && "
                "tc qdisc show dev eth0 && "
                "exec python3 scripts/fleetrmw_quic_gateway_service.py "
                f"--host 0.0.0.0 --port {gateway_port} "
                f"--certificate /work/"
                f"{(gateway_certs / 'server.crt').relative_to(root)} "
                f"--private-key /work/"
                f"{(gateway_certs / 'server.key').relative_to(root)} "
                f"--client-ca /work/"
                f"{(gateway_certs / 'client-ca.crt').relative_to(root)} "
                f"--client-crl /work/"
                f"{(gateway_certs / 'client.crl.pem').relative_to(root)} "
                "--require-client-certificate "
                "--publisher-identity-uri-prefix "
                "spiffe://fleetqox/publishers/ "
                f"--admission-policy /work/{gateway_policy.relative_to(root)} "
                f"--qlog-dir /work/{gateway_service_qlogs.relative_to(root)} "
                "--max-frames-per-topic 8 --max-frame-bytes 65536"
            )
            run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    gateway_name,
                    "--network",
                    network,
                    "--network-alias",
                    gateway_alias,
                    "--cap-add",
                    "NET_ADMIN",
                    "--entrypoint",
                    "bash",
                    "-v",
                    f"{root}:/work",
                    "-w",
                    "/work",
                    image,
                    "-lc",
                    gateway_service_command,
                ]
            )
            gateway_ready = wait_service_ready(gateway_name, timeout_s=10.0)
            if not gateway_ready:
                gateway_start_logs = run(
                    ["docker", "logs", gateway_name], check=False
                )
                raise subprocess.CalledProcessError(
                    1,
                    ["docker", "run", gateway_name],
                    output=gateway_start_logs.stdout,
                    stderr=gateway_start_logs.stderr,
                )
        run([
            "docker", "run", "-d", "--name", router_name, "--network", network,
            "--entrypoint", "bash", "-v", f"{root}:/work", "-w", "/work", image, "-lc",
            "source /opt/ros/jazzy/setup.bash && "
            f"source {install_base}/setup.bash && "
            f"export FLEETQOX_ROUTER_UDP_SOCKET_BUFFER_BYTES={udp_socket_buffer_bytes} && "
            f"{install_base}/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/fleetrmw_udp_router_probe "
            "--bind 0.0.0.0:49700 --expected-frames 0 "
            f"--expected-service-frames {router_expected_service_frames} "
            "--expected-graph-advertisements 12 "
            f"--post-satisfaction-ms {router_post_satisfaction_ms} "
            f"--timeout-ms {router_timeout_ms}",
        ])
        time.sleep(0.4)
        server_command = (
            "source /opt/ros/jazzy/setup.bash\n"
            f"source {install_base}/setup.bash\n"
            "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp\n"
            f"export FLEETQOX_RMW_UDP_SOCKET_BUFFER_BYTES={udp_socket_buffer_bytes}\n"
            f"export FLEETQOX_RMW_UDP_SEND_PACING_US={udp_send_pacing_us}\n"
            f"export FLEETQOX_RMW_SERVICE_REQUEST_REPEATS={service_request_repeats}\n"
            f"export FLEETQOX_RMW_SERVICE_RESPONSE_REPEATS={service_response_repeats}\n"
            f"export FLEETQOX_RMW_SERVICE_REQUEST_REPEAT_INTERVAL_MS={service_request_repeat_interval_ms}\n"
            f"export FLEETQOX_RMW_SERVICE_RESPONSE_REPEAT_INTERVAL_MS={service_response_repeat_interval_ms}\n"
            "export FLEETQOX_RMW_BIND=0.0.0.0:49701\n"
            f"export FLEETQOX_RMW_PEERS={router_name}:49700\n"
            f"export FLEETQOX_SERVER_TIMEOUT_S={server_timeout_s}\n"
            f"export FLEETQOX_EXECUTOR_THREADS={executor_threads}\n"
            f"export FLEETQOX_GOAL_BATCH_SIZE={effective_goal_batch_size}\n"
            f"export FLEETQOX_GOAL_BATCH_TIMEOUT_S={goal_batch_timeout_s}\n"
            f"export FLEETQOX_GOAL_SEND_PACING_MS={goal_send_pacing_ms}\n"
            f"export FLEETQOX_GOAL_BATCH_DELAY_MS={goal_batch_delay_ms}\n"
            f"export FLEETQOX_GOAL_RECREATE_CLIENT_PER_BATCH={int(goal_recreate_client_per_batch)}\n"
            f"export FLEETQOX_RESULT_WINDOW_SIZE={result_window_size}\n"
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
            f"export FLEETQOX_RMW_UDP_SOCKET_BUFFER_BYTES={udp_socket_buffer_bytes}\n"
            f"export FLEETQOX_RMW_UDP_SEND_PACING_US={udp_send_pacing_us}\n"
            f"export FLEETQOX_RMW_SERVICE_REQUEST_REPEATS={service_request_repeats}\n"
            f"export FLEETQOX_RMW_SERVICE_RESPONSE_REPEATS={service_response_repeats}\n"
            f"export FLEETQOX_RMW_SERVICE_REQUEST_REPEAT_INTERVAL_MS={service_request_repeat_interval_ms}\n"
            f"export FLEETQOX_RMW_SERVICE_RESPONSE_REPEAT_INTERVAL_MS={service_response_repeat_interval_ms}\n"
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
            client_netem_prefix
            + "source /opt/ros/jazzy/setup.bash\n"
            f"source {install_base}/setup.bash\n"
            "export RMW_IMPLEMENTATION=rmw_fleetqox_cpp\n"
            f"export FLEETQOX_RMW_UDP_SOCKET_BUFFER_BYTES={udp_socket_buffer_bytes}\n"
            f"export FLEETQOX_RMW_UDP_SEND_PACING_US={udp_send_pacing_us}\n"
            f"export FLEETQOX_RMW_SERVICE_REQUEST_REPEATS={service_request_repeats}\n"
            f"export FLEETQOX_RMW_SERVICE_RESPONSE_REPEATS={service_response_repeats}\n"
            f"export FLEETQOX_RMW_SERVICE_REQUEST_REPEAT_INTERVAL_MS={service_request_repeat_interval_ms}\n"
            f"export FLEETQOX_RMW_SERVICE_RESPONSE_REPEAT_INTERVAL_MS={service_response_repeat_interval_ms}\n"
            f"export FLEETQOX_UPSTREAM_CONCURRENCY={upstream_concurrency}\n"
            f"export FLEETQOX_BATCH_TIMEOUT_S={batch_timeout_s}\n"
            f"export FLEETQOX_GOAL_BATCH_SIZE={effective_goal_batch_size}\n"
            f"export FLEETQOX_GOAL_BATCH_TIMEOUT_S={goal_batch_timeout_s}\n"
            f"export FLEETQOX_GOAL_SEND_PACING_MS={goal_send_pacing_ms}\n"
            f"export FLEETQOX_GOAL_BATCH_DELAY_MS={goal_batch_delay_ms}\n"
            f"export FLEETQOX_GOAL_RECREATE_CLIENT_PER_BATCH={int(goal_recreate_client_per_batch)}\n"
            f"export FLEETQOX_EXECUTOR_THREADS={executor_threads}\n"
            f"export FLEETQOX_RESULT_WINDOW_SIZE={result_window_size}\n"
            "export FLEETQOX_RMW_BIND=0.0.0.0:49702\n"
            f"export FLEETQOX_RMW_PEERS={router_name}:49700\n"
            + live_gateway_environment
            + "python3 - <<'PY'\n"
            + client_python
            + "\nPY\n",
            "--network", network,
            *client_extra_docker_args,
            check=False,
        )
        client_summary = parse_last_json(client.stdout)
        early_client_failed = (
            client.returncode != 0 or client_summary.get("status") != "ok"
        )
        if early_client_failed:
            run(["docker", "stop", "-t", "2", server_name], check=False)
            run(["docker", "stop", "-t", "2", router_name], check=False)
        if live_task_outcome_gateway:
            time.sleep(0.5)
            run(["docker", "stop", "--time", "3", gateway_name], check=False)
            gateway_inspect = run(
                [
                    "docker",
                    "inspect",
                    "-f",
                    "{{.State.ExitCode}}",
                    gateway_name,
                ],
                check=False,
            )
            try:
                gateway_exit_code = int(gateway_inspect.stdout.strip())
            except ValueError:
                gateway_exit_code = -1
            gateway_log_result = run(
                ["docker", "logs", gateway_name], check=False
            )
            gateway_service_logs = (
                gateway_log_result.stdout + gateway_log_result.stderr
            )
            gateway_rows = json_rows(gateway_service_logs)
            gateway_service_summary = gateway_rows[-1] if gateway_rows else {}
            gateway_qlogs = [
                path
                for directory in (gateway_service_qlogs, gateway_client_qlogs)
                for path in directory.glob("*")
                if path.is_file()
            ]
            gateway_qlog_file_count = len(gateway_qlogs)
            gateway_qlog_total_bytes = sum(
                path.stat().st_size for path in gateway_qlogs
            )

        server_wait = run(["docker", "wait", server_name], check=False)
        manager_state = run(
            ["docker", "inspect", "-f", "{{.State.Running}}", manager_name],
            check=False,
        ).stdout.strip()
        manager_running = manager_state == "true"
        run(["docker", "stop", "-t", "2", manager_name], check=False)
        router_wait = run(["docker", "wait", router_name], check=False)
        try:
            server_rc = int(server_wait.stdout.strip())
        except ValueError:
            server_rc = -1
        try:
            router_rc = int(router_wait.stdout.strip())
        except ValueError:
            router_rc = -1
        server_log_result = run(["docker", "logs", server_name], check=False)
        server_logs = server_log_result.stdout + server_log_result.stderr
        manager_log_result = run(["docker", "logs", manager_name], check=False)
        manager_logs = manager_log_result.stdout + manager_log_result.stderr
        router_logs = run(["docker", "logs", router_name], check=False).stdout
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
        task_outcome_mapping_ok = task_outcomes_ok(
            client_summary,
            expected_gateway_submission=None,
        )
        task_outcome_submission_flag_ok = task_outcomes_ok(
            client_summary,
            expected_gateway_submission=live_task_outcome_gateway,
        )
        live_submission_ok = (
            not live_task_outcome_gateway
            or live_task_outcome_submission_ok(client_summary)
        )
        gateway_service_valid = (
            not live_task_outcome_gateway
            or live_task_outcome_service_ok(gateway_service_summary)
        )
        gateway_netem_ok = (
            not live_task_outcome_gateway
            or (
                "qdisc netem" in gateway_service_logs
                and "qdisc netem" in client.stdout
            )
        )
        gateway_qlog_ok = (
            not live_task_outcome_gateway
            or (
                gateway_qlog_file_count >= 2
                and gateway_qlog_total_bytes > 0
            )
        )
        same_process_live_submission = (
            live_task_outcome_gateway
            and task_outcome_mapping_ok
            and live_submission_ok
            and gateway_service_valid
            and gateway_netem_ok
            and gateway_qlog_ok
            and gateway_ready
            and gateway_exit_code == 0
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
            and task_outcome_mapping_ok and task_outcome_submission_flag_ok
            and live_submission_ok and gateway_service_valid
            and gateway_netem_ok and gateway_qlog_ok
            and (not live_task_outcome_gateway or gateway_exit_code == 0)
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok" if status else "failed",
            "nav2_compatible": nav_ok,
            "rmf_compatible": task_ok,
            "nav2_upstream": nav_upstream_ok,
            "rmf_upstream": rmf_upstream_ok,
            "nav2_application_outcome_mapping_claim": task_outcome_mapping_ok,
            "rmf_application_outcome_mapping_claim": task_outcome_mapping_ok,
            "task_outcome_delivery_success_separation_claim": (
                task_outcome_mapping_ok
            ),
            "task_outcome_gateway_submission_performed": (
                client_summary.get(
                    "task_outcome_gateway_submission_performed", False
                )
            ),
            "same_process_live_ros_result_submission_claim": (
                same_process_live_submission
            ),
            "live_task_outcome_gateway_requested": (
                live_task_outcome_gateway
            ),
            "task_outcome_submission_session_reuse_claim": (
                same_process_live_submission
            ),
            "mutual_tls_client_authentication_required": (
                live_task_outcome_gateway
            ),
            "publisher_identity_binding_required": (
                live_task_outcome_gateway
            ),
            "production_quic_backend_claim": False,
            "production_readiness": False,
            "upstream_concurrency": upstream_concurrency,
            "expected_service_frames": expected_service_frames,
            "batch_timeout_s": batch_timeout_s,
            "goal_batch_size": effective_goal_batch_size,
            "goal_batch_count": goal_batch_count,
            "goal_batch_timeout_s": goal_batch_timeout_s,
            "goal_send_pacing_ms": goal_send_pacing_ms,
            "requested_goal_send_pacing_ms": requested_goal_send_pacing_ms,
            "goal_batch_delay_ms": goal_batch_delay_ms,
            "goal_recreate_client_per_batch": goal_recreate_client_per_batch,
            "unwindowed_goal_batch": (
                effective_goal_batch_size == upstream_concurrency
                and goal_batch_count == 1
            ),
            "executor_spin_pacing_enabled": goal_send_pacing_ms > 0.0,
            "nav2_rmf_unwindowed_4096_claim": (
                status
                and upstream_concurrency == 4096
                and effective_goal_batch_size == 4096
                and goal_batch_count == 1
            ),
            "server_timeout_s": server_timeout_s,
            "executor_threads": executor_threads,
            "result_window_size": result_window_size,
            "udp_socket_buffer_bytes": udp_socket_buffer_bytes,
            "udp_send_pacing_us": udp_send_pacing_us,
            "service_request_repeats": service_request_repeats,
            "service_response_repeats": service_response_repeats,
            "service_request_repeat_interval_ms": service_request_repeat_interval_ms,
            "service_response_repeat_interval_ms": service_response_repeat_interval_ms,
            "router_expected_service_frames": router_expected_service_frames,
            "router_post_satisfaction_ms": router_post_satisfaction_ms,
            "router_timeout_ms": router_timeout_ms,
            "navigation_batch": navigation_batch_ok,
            "rmf_batch": rmf_batch_ok,
            "lifecycle_transport": lifecycle_ok,
            "nav2_lifecycle_manager_upstream": lifecycle_ok,
            "manager_running_after_workload": manager_running,
            "client_returncode": client.returncode,
            "server_returncode": server_rc,
            "router_returncode": router_rc,
            "gateway_ready": gateway_ready,
            "gateway_exit_code": gateway_exit_code,
            "gateway_service": gateway_service_summary,
            "gateway_service_valid": gateway_service_valid,
            "gateway_netem_configured_both_containers": gateway_netem_ok,
            "gateway_qlog_file_count": gateway_qlog_file_count,
            "gateway_qlog_total_bytes": gateway_qlog_total_bytes,
            "client": client_summary,
            "server": server_summary,
            "router": router_summary,
            "client_stdout": client.stdout,
            "client_stderr": client.stderr,
            "server_logs": server_logs,
            "manager_logs": manager_logs,
            "router_logs": router_logs,
            "gateway_service_logs": (
                "" if same_process_live_submission else gateway_service_logs
            ),
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
        run(
            [
                "docker",
                "rm",
                "-f",
                router_name,
                server_name,
                manager_name,
                gateway_name,
            ],
            check=False,
        )
        run(["docker", "network", "rm", network], check=False)
        docker_shell(f"rm -rf {build_base} {install_base} {log_base}", check=False)
        if live_task_outcome_gateway:
            shutil.rmtree(gateway_temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
