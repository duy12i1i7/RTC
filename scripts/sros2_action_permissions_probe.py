#!/usr/bin/env python3
"""Exercise SROS2-generated Action call/execute permissions through rclpy."""

from __future__ import annotations

import argparse
import ctypes
import json
import time
import traceback
from typing import Any, Callable


SCHEMA_VERSION = "fleetrmw.sros2_action_permissions_probe.v1"
DEFAULT_ENCLAVE = "/fleetqox/security_probe"
DEFAULT_DOMAIN_ID = 7
ALLOWED_ACTION = "/fleetqox/lookup_transform"
CALL_DENIED_ACTION = "/fleetqox/lookup_transform_call_denied"
EXECUTE_DENIED_ACTION = "/fleetqox/lookup_transform_execute_denied"
DEFAULT_DENIED_ACTION = "/fleetqox/lookup_transform_default_denied"


def spin_until(executor: Any, predicate: Callable[[], bool], timeout_sec: float) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        executor.spin_once(timeout_sec=min(0.05, max(deadline - time.monotonic(), 0.0)))
        if predicate():
            return True
    return predicate()


def bind_runtime() -> ctypes.CDLL:
    runtime = ctypes.CDLL("librmw_fleetqox_cpp.so", mode=ctypes.RTLD_GLOBAL)
    runtime.rmw_fleetqox_cpp_sros2_permissions_xml_loaded.restype = ctypes.c_bool
    runtime.rmw_fleetqox_cpp_sros2_runtime_signature_verified.restype = ctypes.c_bool
    runtime.rmw_fleetqox_cpp_sros2_permissions_xml_error.restype = ctypes.c_char_p
    runtime.rmw_fleetqox_cpp_sros2_topic_authorization_decision.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_size_t,
    ]
    runtime.rmw_fleetqox_cpp_sros2_topic_authorization_decision.restype = ctypes.c_int
    for metric in metric_names():
        getattr(runtime, metric).restype = ctypes.c_uint64
    return runtime


def metric_names() -> tuple[str, ...]:
    return (
        "rmw_fleetqox_cpp_sros2_permissions_xml_allowed",
        "rmw_fleetqox_cpp_sros2_permissions_xml_denied",
        "rmw_fleetqox_cpp_sros2_permissions_xml_parse_errors",
        "rmw_fleetqox_cpp_sros2_permissions_xml_subscribe_allowed",
        "rmw_fleetqox_cpp_sros2_permissions_xml_subscribe_denied",
        "rmw_fleetqox_cpp_sros2_service_request_publish_allowed",
        "rmw_fleetqox_cpp_sros2_service_request_publish_denied",
        "rmw_fleetqox_cpp_sros2_service_request_subscribe_allowed",
        "rmw_fleetqox_cpp_sros2_service_request_subscribe_denied",
        "rmw_fleetqox_cpp_sros2_service_response_publish_allowed",
        "rmw_fleetqox_cpp_sros2_service_response_publish_denied",
        "rmw_fleetqox_cpp_sros2_service_response_subscribe_allowed",
        "rmw_fleetqox_cpp_sros2_service_response_subscribe_denied",
        "rmw_fleetqox_cpp_sros2_service_authorization_parse_errors",
    )


def metric_snapshot(runtime: ctypes.CDLL) -> dict[str, int]:
    return {name.removeprefix("rmw_fleetqox_cpp_"): int(getattr(runtime, name)())
            for name in metric_names()}


def metric_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {name: after[name] - before[name] for name in before}


def authorization_decision(
    runtime: ctypes.CDLL,
    operation: str,
    topic: str,
    enclave: str,
    domain_id: int,
) -> int:
    return int(runtime.rmw_fleetqox_cpp_sros2_topic_authorization_decision(
        operation.encode(), topic.encode(), enclave.encode(), domain_id))


def action_decision_matrix(
    runtime: ctypes.CDLL,
    action_name: str,
    enclave: str,
    domain_id: int,
) -> dict[str, int]:
    request = f"rq{action_name}/_action/send_goalRequest"
    response = f"rr{action_name}/_action/send_goalReply"
    feedback = f"{action_name}/_action/feedback"
    status = f"{action_name}/_action/status"
    return {
        "call_request_publish": authorization_decision(
            runtime, "publish", request, enclave, domain_id),
        "execute_request_subscribe": authorization_decision(
            runtime, "subscribe", request, enclave, domain_id),
        "execute_response_publish": authorization_decision(
            runtime, "publish", response, enclave, domain_id),
        "call_response_subscribe": authorization_decision(
            runtime, "subscribe", response, enclave, domain_id),
        "execute_feedback_publish": authorization_decision(
            runtime, "publish", feedback, enclave, domain_id),
        "call_feedback_subscribe": authorization_decision(
            runtime, "subscribe", feedback, enclave, domain_id),
        "execute_status_publish": authorization_decision(
            runtime, "publish", status, enclave, domain_id),
        "call_status_subscribe": authorization_decision(
            runtime, "subscribe", status, enclave, domain_id),
    }


def expected_action_decisions(call: int, execute: int) -> dict[str, int]:
    return {
        "call_request_publish": call,
        "execute_request_subscribe": execute,
        "execute_response_publish": execute,
        "call_response_subscribe": call,
        "execute_feedback_publish": execute,
        "call_feedback_subscribe": call,
        "execute_status_publish": execute,
        "call_status_subscribe": call,
    }


def run_probe(*, enclave: str, domain_id: int, timeout_sec: float) -> dict[str, Any]:
    import rclpy
    from rclpy.action import ActionClient, ActionServer
    from rclpy.executors import MultiThreadedExecutor
    from tf2_msgs.action import LookupTransform

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "pending",
        "enclave": enclave,
        "domain_id": domain_id,
        "action_type": "tf2_msgs/action/LookupTransform",
        "allowed_action": ALLOWED_ACTION,
        "call_denied_action": CALL_DENIED_ACTION,
        "execute_denied_action": EXECUTE_DENIED_ACTION,
    }
    executor = None
    server_node = None
    client_node = None
    entities: list[Any] = []
    try:
        rclpy.init(
            args=["--ros-args", "--enclave", enclave],
            domain_id=domain_id,
        )
        runtime = bind_runtime()
        summary["policy_loaded"] = bool(
            runtime.rmw_fleetqox_cpp_sros2_permissions_xml_loaded())
        summary["runtime_signature_verified"] = bool(
            runtime.rmw_fleetqox_cpp_sros2_runtime_signature_verified())
        error = runtime.rmw_fleetqox_cpp_sros2_permissions_xml_error()
        summary["permissions_xml_error"] = error.decode() if error else ""

        decision_matrices = {
            "allowed": action_decision_matrix(
                runtime, ALLOWED_ACTION, enclave, domain_id),
            "call_denied": action_decision_matrix(
                runtime, CALL_DENIED_ACTION, enclave, domain_id),
            "execute_denied": action_decision_matrix(
                runtime, EXECUTE_DENIED_ACTION, enclave, domain_id),
            "default_denied": action_decision_matrix(
                runtime, DEFAULT_DENIED_ACTION, enclave, domain_id),
        }
        summary["decision_matrices"] = decision_matrices
        decision_matrix_ok = (
            decision_matrices["allowed"] == expected_action_decisions(1, 1)
            and decision_matrices["call_denied"] == expected_action_decisions(2, 1)
            and decision_matrices["execute_denied"] == expected_action_decisions(1, 2)
            and decision_matrices["default_denied"] == expected_action_decisions(2, 2)
        )
        summary["action_call_execute_decision_matrix_claim"] = decision_matrix_ok

        metrics_before = metric_snapshot(runtime)
        server_node = rclpy.create_node("sros2_action_server", namespace="/fleetqox")
        client_node = rclpy.create_node("sros2_action_client", namespace="/fleetqox")
        executor = MultiThreadedExecutor(num_threads=4)
        executor.add_node(server_node)
        executor.add_node(client_node)

        allowed_events: list[str] = []
        feedback_events: list[str] = []

        def execute_allowed(goal_handle: Any) -> Any:
            allowed_events.append("execute")
            goal_handle.publish_feedback(LookupTransform.Feedback())
            allowed_events.append("feedback_published")
            result = LookupTransform.Result()
            result.transform.header.frame_id = goal_handle.request.target_frame
            result.transform.child_frame_id = goal_handle.request.source_frame
            result.transform.transform.rotation.w = 1.0
            result.error.error = 0
            result.error.error_string = "ok"
            goal_handle.succeed()
            return result

        allowed_server = ActionServer(
            server_node, LookupTransform, ALLOWED_ACTION, execute_allowed)
        allowed_client = ActionClient(client_node, LookupTransform, ALLOWED_ACTION)
        entities.extend((allowed_server, allowed_client))
        summary["allowed_server_available"] = spin_until(
            executor, allowed_client.server_is_ready, timeout_sec)

        allowed_goal = LookupTransform.Goal()
        allowed_goal.target_frame = "map"
        allowed_goal.source_frame = "base_link"
        send_future = allowed_client.send_goal_async(
            allowed_goal,
            feedback_callback=lambda _message: feedback_events.append("feedback_received"),
        )
        summary["allowed_send_done"] = spin_until(
            executor, send_future.done, timeout_sec)
        if send_future.done() and send_future.exception() is None:
            goal_handle = send_future.result()
            summary["allowed_goal_accepted"] = bool(goal_handle.accepted)
            if goal_handle.accepted:
                result_future = goal_handle.get_result_async()
                summary["allowed_result_done"] = spin_until(
                    executor, result_future.done, timeout_sec)
                if result_future.done() and result_future.exception() is None:
                    result_wrapper = result_future.result()
                    result = result_wrapper.result
                    summary["allowed_result_status"] = int(result_wrapper.status)
                    summary["allowed_result_frame"] = result.transform.header.frame_id
                    summary["allowed_result_child_frame"] = (
                        result.transform.child_frame_id)
                    summary["allowed_result_error"] = int(result.error.error)
                    summary["allowed_result_error_string"] = result.error.error_string
        spin_until(executor, lambda: bool(feedback_events), min(timeout_sec, 1.0))
        summary["allowed_events"] = allowed_events
        summary["allowed_feedback_events"] = feedback_events
        allowed_ok = (
            summary.get("allowed_server_available") is True
            and summary.get("allowed_send_done") is True
            and summary.get("allowed_goal_accepted") is True
            and summary.get("allowed_result_done") is True
            and summary.get("allowed_result_status") == 4
            and summary.get("allowed_result_frame") == "map"
            and summary.get("allowed_result_child_frame") == "base_link"
            and summary.get("allowed_result_error") == 0
            and "execute" in allowed_events
            and "feedback_published" in allowed_events
            and "feedback_received" in feedback_events
        )
        summary["sros2_action_allowed_end_to_end_claim"] = allowed_ok
        allowed_client.destroy()
        allowed_server.destroy()
        entities.clear()

        call_denied_events: list[str] = []

        def execute_call_denied(goal_handle: Any) -> Any:
            call_denied_events.append("execute")
            result = LookupTransform.Result()
            goal_handle.succeed()
            return result

        call_denied_server = ActionServer(
            server_node,
            LookupTransform,
            CALL_DENIED_ACTION,
            execute_call_denied,
        )
        call_denied_client = ActionClient(
            client_node, LookupTransform, CALL_DENIED_ACTION)
        entities.extend((call_denied_server, call_denied_client))
        summary["call_denied_server_available"] = spin_until(
            executor, call_denied_client.server_is_ready, timeout_sec)
        denied_goal = LookupTransform.Goal()
        denied_goal.target_frame = "map"
        denied_goal.source_frame = "denied"
        denied_exception = ""
        denied_future = None
        call_denied_publish_before = metric_snapshot(runtime)[
            "sros2_service_request_publish_denied"]
        try:
            denied_future = call_denied_client.send_goal_async(denied_goal)
        except Exception as exc:  # rclpy converts RMW_RET_ERROR into RCLError.
            denied_exception = repr(exc)
        if denied_future is not None:
            spin_until(executor, denied_future.done, min(timeout_sec, 0.5))
            if denied_future.done() and denied_future.exception() is not None:
                denied_exception = repr(denied_future.exception())
        spin_until(executor, lambda: bool(call_denied_events), 0.1)
        call_denied_publish_after = metric_snapshot(runtime)[
            "sros2_service_request_publish_denied"]
        summary["call_denied_exception"] = denied_exception
        summary["call_denied_future_created"] = denied_future is not None
        summary["call_denied_future_done"] = (
            denied_future.done() if denied_future is not None else False)
        summary["call_denied_events"] = call_denied_events
        summary["call_denied_request_publish_denied_delta"] = (
            call_denied_publish_after - call_denied_publish_before)
        call_denied_ok = (
            summary.get("call_denied_server_available") is True
            and bool(denied_exception)
            and "SROS2 permissions policy" in denied_exception
            and call_denied_events == []
            and summary["call_denied_request_publish_denied_delta"] >= 1
        )
        summary["sros2_action_call_denied_fail_closed_claim"] = call_denied_ok
        call_denied_client.destroy()
        call_denied_server.destroy()
        entities.clear()

        execute_denied_events: list[str] = []

        def execute_execute_denied(goal_handle: Any) -> Any:
            execute_denied_events.append("execute")
            result = LookupTransform.Result()
            goal_handle.succeed()
            return result

        execute_denied_server = ActionServer(
            server_node,
            LookupTransform,
            EXECUTE_DENIED_ACTION,
            execute_execute_denied,
        )
        execute_denied_client = ActionClient(
            client_node, LookupTransform, EXECUTE_DENIED_ACTION)
        entities.extend((execute_denied_server, execute_denied_client))
        summary["execute_denied_server_available"] = spin_until(
            executor, execute_denied_client.server_is_ready, min(timeout_sec, 0.5))
        execute_goal = LookupTransform.Goal()
        execute_goal.target_frame = "map"
        execute_goal.source_frame = "execute_denied"
        execute_subscribe_before = metric_snapshot(runtime)[
            "sros2_service_request_subscribe_denied"]
        execute_denied_exception = ""
        execute_denied_future = None
        try:
            execute_denied_future = execute_denied_client.send_goal_async(execute_goal)
            spin_until(executor, execute_denied_future.done, 0.35)
        except Exception as exc:
            execute_denied_exception = repr(exc)
        execute_subscribe_after = metric_snapshot(runtime)[
            "sros2_service_request_subscribe_denied"]
        summary["execute_denied_exception"] = execute_denied_exception
        summary["execute_denied_future_created"] = execute_denied_future is not None
        summary["execute_denied_future_done"] = (
            execute_denied_future.done() if execute_denied_future is not None else False)
        summary["execute_denied_events"] = execute_denied_events
        summary["execute_denied_request_subscribe_denied_delta"] = (
            execute_subscribe_after - execute_subscribe_before)
        execute_denied_ok = (
            summary.get("execute_denied_server_available") is True
            and execute_denied_exception == ""
            and execute_denied_future is not None
            and not execute_denied_future.done()
            and execute_denied_events == []
            and summary["execute_denied_request_subscribe_denied_delta"] >= 1
        )
        summary["sros2_action_execute_denied_fail_closed_claim"] = execute_denied_ok
        execute_denied_client.destroy()
        execute_denied_server.destroy()
        entities.clear()

        metrics_after = metric_snapshot(runtime)
        deltas = metric_delta(metrics_before, metrics_after)
        summary["authorization_metric_deltas"] = deltas
        metrics_ok = (
            deltas["sros2_service_request_publish_allowed"] >= 3
            and deltas["sros2_service_request_publish_denied"] >= 1
            and deltas["sros2_service_request_subscribe_allowed"] >= 2
            and deltas["sros2_service_request_subscribe_denied"] >= 1
            and deltas["sros2_service_response_publish_allowed"] >= 2
            and deltas["sros2_service_response_subscribe_allowed"] >= 2
            and deltas["sros2_permissions_xml_allowed"] >= 1
            and deltas["sros2_permissions_xml_subscribe_allowed"] >= 1
            and deltas["sros2_permissions_xml_parse_errors"] == 0
            and deltas["sros2_service_authorization_parse_errors"] == 0
        )
        summary["sros2_action_authorization_metrics_claim"] = metrics_ok
        action_ok = (
            summary["policy_loaded"]
            and summary["runtime_signature_verified"]
            and summary["permissions_xml_error"] == ""
            and decision_matrix_ok
            and allowed_ok
            and call_denied_ok
            and execute_denied_ok
            and metrics_ok
        )
        summary["sros2_action_authorization_claim"] = action_ok
        summary["status"] = "ok" if action_ok else "failed"
    except Exception as exc:
        summary["status"] = "exception"
        summary["exception"] = repr(exc)
        summary["traceback"] = traceback.format_exc()
        summary.setdefault("sros2_action_authorization_claim", False)
    finally:
        if executor is not None:
            try:
                executor.shutdown()
            except Exception:
                pass
        for entity in reversed(entities):
            try:
                entity.destroy()
            except Exception:
                pass
        for node in (client_node, server_node):
            if node is not None:
                try:
                    node.destroy_node()
                except Exception:
                    pass
        try:
            rclpy.shutdown()
        except Exception:
            pass
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enclave", default=DEFAULT_ENCLAVE)
    parser.add_argument("--domain-id", type=int, default=DEFAULT_DOMAIN_ID)
    parser.add_argument("--timeout-sec", type=float, default=3.0)
    args = parser.parse_args()
    summary = run_probe(
        enclave=args.enclave,
        domain_id=args.domain_id,
        timeout_sec=max(args.timeout_sec, 0.5),
    )
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
