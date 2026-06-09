"""Apply FleetRMW local control leases to typed ROS 2 Twist commands."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import time
from pathlib import Path

from fleetqox.local_control_lease import (
    ControlLease,
    LeaseDecision,
    LeasePolicy,
    LocalControlLeaseState,
    TwistCommand,
    load_lease_policy,
)
from fleetqox.sidecar_runtime import RobotFeedbackTcpClient, send_robot_feedback


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robot-id", default="robot_0000")
    parser.add_argument("--robot-count", type=int, default=1)
    parser.add_argument("--lease-topic")
    parser.add_argument("--typed-cmd-topic")
    parser.add_argument("--safe-cmd-topic")
    parser.add_argument("--decision-log", type=Path, default=Path("results_ros2_live_bridge/local_controller_lease.jsonl"))
    parser.add_argument("--profile-config", type=Path)
    parser.add_argument("--controller-profile")
    parser.add_argument("--max-linear-x", type=float)
    parser.add_argument("--max-angular-z", type=float)
    parser.add_argument("--max-linear-accel-x", type=float)
    parser.add_argument("--max-angular-accel-z", type=float)
    parser.add_argument("--max-linear-jerk-x", type=float)
    parser.add_argument("--max-angular-jerk-z", type=float)
    parser.add_argument("--max-local-lifespan-ms", type=float)
    parser.add_argument("--expiry-action", choices=("stop", "hold_last", "drop"))
    parser.add_argument("--timer-period-s", type=float, default=0.02)
    parser.add_argument("--idle-timeout-s", type=float, default=4.0)
    parser.add_argument("--max-runtime-s", type=float, default=120.0)
    parser.add_argument("--feedback-sidecar-host")
    parser.add_argument("--feedback-sidecar-port", type=int, default=8765)
    parser.add_argument("--feedback-timeout-s", type=float, default=0.25)
    parser.add_argument("--feedback-every-decisions", type=int, default=12)
    args = parser.parse_args()

    try:
        import rclpy
        from geometry_msgs.msg import Twist
        from std_msgs.msg import String
    except ImportError as exc:
        raise SystemExit("ROS 2 rclpy, geometry_msgs, and std_msgs are required for local lease controller") from exc

    robot_ids = robot_ids_for_args(args.robot_id, args.robot_count)

    args.decision_log.parent.mkdir(parents=True, exist_ok=True)

    rclpy.init()
    node = rclpy.create_node("fleetrmw_local_controller_lease")
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
    subscriptions = []
    timers = []

    with args.decision_log.open("w", encoding="utf-8") as handle:

        def bump(robot_id: str, key: str) -> None:
            counters[key] += 1
            counters_by_robot[robot_id][key] += 1

        def emit(
            decision: LeaseDecision,
            *,
            robot_id: str,
            event_type: str,
            safe_cmd_topic: str,
            publisher,
            lease_state: LocalControlLeaseState,
        ) -> None:
            nonlocal last_activity
            last_activity = time.monotonic()
            record = decision.as_log_record()
            record["event_type"] = event_type
            record["robot_id"] = robot_id
            record["safe_cmd_topic"] = safe_cmd_topic
            record["controller_profile"] = lease_state.policy.controller_profile
            record["expiry_action"] = lease_state.policy.expiry_action
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            feedback_record = local_controller_feedback_record(record)
            if feedback_record is not None:
                feedback_window.append(feedback_record)
                sent, failed = flush_feedback_window(
                    args,
                    feedback_window,
                    feedback_client=feedback_client,
                )
                counters["feedback_sent"] += sent
                counters["feedback_failed"] += failed
            if decision.publish:
                publisher.publish(twist_from_command(Twist, decision.safe_command))
                bump(robot_id, "published")

        def lease_callback_for(
            *,
            robot_id: str,
            lease_state: LocalControlLeaseState,
            safe_cmd_topic: str,
            publisher,
        ):
            def _callback(message: String) -> None:
                now_ms = monotonic_ms()
                try:
                    lease = ControlLease.from_envelope(
                        message.data,
                        received_monotonic_ms=now_ms,
                        policy=lease_state.policy,
                    )
                    decision = lease_state.ingest_lease(lease)
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    decision = LeaseDecision(
                        status="invalid_lease",
                        reason=str(exc),
                        publish=False,
                        safe_command=TwistCommand.zero(),
                        requested_command=None,
                        lease=None,
                        now_ms=now_ms,
                    )
                bump(robot_id, "lease")
                emit(
                    decision,
                    robot_id=robot_id,
                    event_type="lease",
                    safe_cmd_topic=safe_cmd_topic,
                    publisher=publisher,
                    lease_state=lease_state,
                )

            return _callback

        def command_callback_for(
            *,
            robot_id: str,
            lease_state: LocalControlLeaseState,
            safe_cmd_topic: str,
            publisher,
        ):
            def _callback(message: Twist) -> None:
                now_ms = monotonic_ms()
                command = command_from_twist(message)
                decision = lease_state.evaluate_command(command, now_ms=now_ms)
                bump(robot_id, "command")
                emit(
                    decision,
                    robot_id=robot_id,
                    event_type="command",
                    safe_cmd_topic=safe_cmd_topic,
                    publisher=publisher,
                    lease_state=lease_state,
                )

            return _callback

        def timer_callback_for(
            *,
            robot_id: str,
            lease_state: LocalControlLeaseState,
            safe_cmd_topic: str,
            publisher,
        ):
            def _callback() -> None:
                decision = lease_state.tick(now_ms=monotonic_ms())
                if decision is not None:
                    bump(robot_id, "timer")
                    emit(
                        decision,
                        robot_id=robot_id,
                        event_type="timer",
                        safe_cmd_topic=safe_cmd_topic,
                        publisher=publisher,
                        lease_state=lease_state,
                    )

            return _callback

        for robot_id in robot_ids:
            lease_state = LocalControlLeaseState(policy_from_args(args))
            lease_topic = topic_for_robot(
                args.lease_topic,
                default_template="/fleetrmw/{robot_id}/control_lease",
                base_robot_id=args.robot_id,
                robot_id=robot_id,
            )
            typed_cmd_topic = topic_for_robot(
                args.typed_cmd_topic,
                default_template="/fleetrmw/{robot_id}/local_cmd_vel",
                base_robot_id=args.robot_id,
                robot_id=robot_id,
            )
            safe_cmd_topic = topic_for_robot(
                args.safe_cmd_topic,
                default_template="/{robot_id}/cmd_vel_fleetrmw",
                base_robot_id=args.robot_id,
                robot_id=robot_id,
            )
            publisher = node.create_publisher(Twist, safe_cmd_topic, 10)
            subscriptions.append(
                node.create_subscription(
                    String,
                    lease_topic,
                    lease_callback_for(
                        robot_id=robot_id,
                        lease_state=lease_state,
                        safe_cmd_topic=safe_cmd_topic,
                        publisher=publisher,
                    ),
                    10,
                )
            )
            subscriptions.append(
                node.create_subscription(
                    Twist,
                    typed_cmd_topic,
                    command_callback_for(
                        robot_id=robot_id,
                        lease_state=lease_state,
                        safe_cmd_topic=safe_cmd_topic,
                        publisher=publisher,
                    ),
                    10,
                )
            )
            timers.append(
                node.create_timer(
                    args.timer_period_s,
                    timer_callback_for(
                        robot_id=robot_id,
                        lease_state=lease_state,
                        safe_cmd_topic=safe_cmd_topic,
                        publisher=publisher,
                    ),
                )
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
            for timer in timers:
                node.destroy_timer(timer)
            for subscription in subscriptions:
                node.destroy_subscription(subscription)
            node.destroy_node()
            rclpy.shutdown()

    print(
        "local_controller "
        f"robot_count={len(robot_ids)} leases={counters['lease']} "
        f"commands={counters['command']} published={counters['published']} "
        f"feedback_sent={counters['feedback_sent']} feedback_failed={counters['feedback_failed']} "
        f"by_robot={{{', '.join(f'{robot}:dict({dict(counts)})' for robot, counts in counters_by_robot.items())}}}"
    )


def local_controller_feedback_record(
    record: dict[str, object],
) -> dict[str, object] | None:
    event_type = str(record.get("event_type", ""))
    requested_command = record.get("requested_command")
    if event_type != "command" and requested_command is None:
        return None
    robot_id = str(record.get("robot_id", "") or "")
    if not robot_id:
        lease = record.get("lease")
        if isinstance(lease, dict):
            robot_id = str(lease.get("robot_id", "") or "")
    if not robot_id:
        return None

    published = bool(record.get("publish"))
    feedback: dict[str, object] = {
        "schema_version": "fleetrmw.robot_feedback.v1",
        "source": "local_controller",
        "robot_id": robot_id,
        "flow_class": "control",
        "event_type": "command",
        "control_delivered": published,
        "control_delivery_ratio": 1.0 if published else 0.0,
        "feedback_sample_count": 1,
    }
    lease = record.get("lease")
    if isinstance(lease, dict):
        feedback["flow_id"] = str(lease.get("flow_id", "") or "")
        feedback["event_id"] = lease.get("event_id")
        feedback["action"] = str(lease.get("action", "") or "")
        feedback["wire_mode"] = str(lease.get("wire_mode", "") or "")
        now_ms = feedback_float(record.get("now_ms"))
        expires_at = feedback_float(lease.get("local_expires_at_ms"))
        if now_ms is not None and expires_at is not None:
            feedback["deadline_met"] = bool(published and now_ms <= expires_at)
        deadline_ms = feedback_float(lease.get("deadline_ms"))
        if deadline_ms is not None:
            feedback["deadline_ms"] = deadline_ms
    return feedback


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


def monotonic_ms() -> float:
    return time.monotonic() * 1000.0


def policy_from_args(args: argparse.Namespace) -> LeasePolicy:
    overrides = {
        "max_linear_x": args.max_linear_x,
        "max_abs_angular_z": args.max_angular_z,
        "max_linear_accel_x": args.max_linear_accel_x,
        "max_abs_angular_accel_z": args.max_angular_accel_z,
        "max_linear_jerk_x": args.max_linear_jerk_x,
        "max_abs_angular_jerk_z": args.max_angular_jerk_z,
        "max_local_lifespan_ms": args.max_local_lifespan_ms,
        "expiry_action": args.expiry_action,
    }
    if args.profile_config:
        return load_lease_policy(
            args.profile_config,
            profile_name=args.controller_profile,
            overrides=overrides,
        )
    base = LeasePolicy(controller_profile=args.controller_profile or "diff_drive_safe_v1")
    merged = {
        "max_linear_x": base.max_linear_x,
        "max_abs_linear_y": base.max_abs_linear_y,
        "max_abs_linear_z": base.max_abs_linear_z,
        "max_abs_angular_x": base.max_abs_angular_x,
        "max_abs_angular_y": base.max_abs_angular_y,
        "max_abs_angular_z": base.max_abs_angular_z,
        "max_linear_accel_x": base.max_linear_accel_x,
        "max_abs_angular_accel_z": base.max_abs_angular_accel_z,
        "max_linear_jerk_x": base.max_linear_jerk_x,
        "max_abs_angular_jerk_z": base.max_abs_angular_jerk_z,
        "max_local_lifespan_ms": base.max_local_lifespan_ms,
        "pending_command_window_ms": base.pending_command_window_ms,
        "publish_stop_on_expiry": base.publish_stop_on_expiry,
        "expiry_action": base.expiry_action,
    }
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value
    return LeasePolicy.from_mapping(base.controller_profile, merged)


def command_from_twist(message) -> TwistCommand:
    return TwistCommand(
        linear_x=float(message.linear.x),
        linear_y=float(message.linear.y),
        linear_z=float(message.linear.z),
        angular_x=float(message.angular.x),
        angular_y=float(message.angular.y),
        angular_z=float(message.angular.z),
    )


def twist_from_command(twist_cls, command: TwistCommand):
    message = twist_cls()
    message.linear.x = command.linear_x
    message.linear.y = command.linear_y
    message.linear.z = command.linear_z
    message.angular.x = command.angular_x
    message.angular.y = command.angular_y
    message.angular.z = command.angular_z
    return message


if __name__ == "__main__":
    main()
