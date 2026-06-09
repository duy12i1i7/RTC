"""Publish sidecar UDP packet events back into ROS 2 egress topics."""

from __future__ import annotations

import argparse
import json
import math
import socket
import time
from pathlib import Path

from fleetqox.projection_quality_ros import (
    FLEETRMW_PROJECTION_QUALITY_MSG_TYPE,
    FLEETRMW_QUALIFIED_LASER_SCAN_MSG_TYPE,
    FLEETRMW_QUALIFIED_ODOMETRY_MSG_TYPE,
    assign_projection_quality_message,
    projection_quality_message_from_payload,
)
from fleetqox.rmw_ack import RmwAckNackTracker
from fleetqox.sidecar_egress import EgressPublication, SidecarEgressRouter, decode_sidecar_packet
from fleetqox.sidecar_egress import robot_feedback_record_from_event
from fleetqox.sidecar_runtime import RobotFeedbackTcpClient, send_robot_feedback


FEEDBACK_DEADLINE_CLASSES = {"safety", "control", "coordination", "state"}
FEEDBACK_LATENCY_CLASSES = FEEDBACK_DEADLINE_CLASSES | {"human_qoe"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=9100)
    parser.add_argument("--topic-prefix", default="/fleetrmw")
    parser.add_argument("--node-name", default="fleetrmw_egress_bridge")
    parser.add_argument("--publication-log", type=Path, default=Path("results_ros2_live_bridge/egress_publications.jsonl"))
    parser.add_argument("--forward-host")
    parser.add_argument("--forward-port", type=int, default=9100)
    parser.add_argument("--feedback-sidecar-host")
    parser.add_argument("--feedback-sidecar-port", type=int, default=8765)
    parser.add_argument("--feedback-timeout-s", type=float, default=0.25)
    parser.add_argument("--feedback-every-packets", type=int, default=12)
    parser.add_argument("--feedback-control-lease-ack-immediate", action="store_true")
    parser.add_argument("--feedback-control-lease-ack-window-events", type=int, default=0)
    parser.add_argument("--feedback-control-lease-ack-adaptive", action="store_true")
    parser.add_argument("--feedback-control-lease-ack-adaptive-min-events", type=int, default=8)
    parser.add_argument("--feedback-control-lease-ack-adaptive-max-events", type=int, default=48)
    parser.add_argument("--feedback-control-lease-ack-adaptive-success-step", type=int, default=1)
    parser.add_argument("--feedback-control-lease-ack-adaptive-failure-multiplier", type=float, default=2.0)
    parser.add_argument("--feedback-control-lease-ack-adaptive-max-age-ms", type=float, default=120.0)
    parser.add_argument(
        "--feedback-control-lease-ack-adaptive-no-piggyback-first",
        action="store_false",
        dest="feedback_control_lease_ack_adaptive_piggyback_first",
        default=True,
    )
    parser.add_argument("--publish-typed", action="store_true")
    parser.add_argument("--projection-quality-delivery-mode", choices=("sideband", "wrapper", "both"), default="wrapper")
    parser.add_argument("--projection-quality-payload-mode", choices=("compact", "full"), default="compact")
    parser.add_argument("--projection-quality-message-mode", choices=("string", "typed"), default="typed")
    parser.add_argument("--idle-timeout-s", type=float, default=4.0)
    parser.add_argument("--max-runtime-s", type=float, default=120.0)
    parser.add_argument("--socket-timeout-s", type=float, default=0.1)
    parser.add_argument("--no-validate", action="store_true")
    args = parser.parse_args()

    try:
        import rclpy
        from geometry_msgs.msg import Twist
        from nav_msgs.msg import Odometry
        from sensor_msgs.msg import LaserScan
        from std_msgs.msg import String
        ProjectionQualityMsg = None
        QualifiedOdometry = None
        QualifiedLaserScan = None
        if args.projection_quality_message_mode == "typed" or args.projection_quality_delivery_mode in {"wrapper", "both"}:
            from fleetrmw_interfaces.msg import (
                ProjectionQuality as ProjectionQualityMsg,
                QualifiedLaserScan,
                QualifiedOdometry,
            )
    except ImportError as exc:
        raise SystemExit(
            "ROS 2 rclpy, geometry_msgs, nav_msgs, sensor_msgs, std_msgs, and fleetrmw_interfaces are required for live egress bridge"
        ) from exc

    args.publication_log.parent.mkdir(parents=True, exist_ok=True)
    projection_quality_msg_type = (
        FLEETRMW_PROJECTION_QUALITY_MSG_TYPE
        if args.projection_quality_message_mode == "typed"
        else "std_msgs/msg/String"
    )
    router = SidecarEgressRouter(
        topic_prefix=args.topic_prefix,
        enable_typed_reconstruction=args.publish_typed,
        include_projection_payload=args.projection_quality_payload_mode == "full",
        projection_quality_msg_type=projection_quality_msg_type,
        projection_quality_delivery=args.projection_quality_delivery_mode,
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    forward_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if args.forward_host else None
    sock.bind((args.listen_host, args.listen_port))
    sock.settimeout(args.socket_timeout_s)

    rclpy.init()
    node = rclpy.create_node(args.node_name)
    publishers = {}
    started = time.monotonic()
    last_packet = started
    packets = 0
    invalid = 0
    forwarded = 0
    published = 0
    feedback_sent = 0
    feedback_failed = 0
    feedback_windows: dict[str, dict[str, float]] = {}
    immediate_ack_seen: set[tuple[str, int]] = set()
    control_lease_ack_window: list[dict[str, object]] = []
    ack_nack_tracker = RmwAckNackTracker()
    feedback_client = (
        RobotFeedbackTcpClient(
            host=args.feedback_sidecar_host,
            port=args.feedback_sidecar_port,
            timeout_s=args.feedback_timeout_s,
        )
        if args.feedback_sidecar_host
        else None
    )
    adaptive_ack_pacer = (
        ControlLeaseAckPacer.from_args(args)
        if args.feedback_control_lease_ack_adaptive
        else None
    )

    try:
        with args.publication_log.open("w", encoding="utf-8") as handle:
            while True:
                now = time.monotonic()
                if now - started > args.max_runtime_s:
                    break
                if packets and now - last_packet > args.idle_timeout_s:
                    break
                try:
                    data, address = sock.recvfrom(2_000_000)
                except socket.timeout:
                    if adaptive_ack_pacer is not None and args.feedback_sidecar_host:
                        sent, failed = adaptive_ack_pacer.flush_if_due(
                            args,
                            feedback_client=feedback_client,
                        )
                        feedback_sent += sent
                        feedback_failed += failed
                    rclpy.spin_once(node, timeout_sec=0.0)
                    continue

                packets += 1
                last_packet = time.monotonic()
                recv_ns = time.monotonic_ns()
                if forward_sock and args.forward_host:
                    forward_sock.sendto(data, (args.forward_host, args.forward_port))
                    forwarded += 1

                event = decode_sidecar_packet(data, validate=not args.no_validate)
                if event is None:
                    invalid += 1
                    continue
                if args.feedback_sidecar_host:
                    feedback_record = robot_feedback_record_from_event(
                        event,
                        recv_monotonic_ns=recv_ns,
                    )
                    if feedback_record is not None:
                        ack_nack_record = ack_nack_tracker.observe(feedback_record)
                        update_feedback_window(
                            feedback_windows,
                            feedback_record,
                            ack_nack_record=ack_nack_record,
                        )
                        if args.feedback_control_lease_ack_immediate:
                            sent, failed = maybe_send_immediate_control_lease_ack(
                                args,
                                feedback_record,
                                seen=immediate_ack_seen,
                                feedback_client=feedback_client,
                            )
                            feedback_sent += sent
                            feedback_failed += failed
                        elif adaptive_ack_pacer is not None:
                            sent, failed = adaptive_ack_pacer.maybe_ack(
                                args,
                                feedback_record,
                                feedback_client=feedback_client,
                            )
                            feedback_sent += sent
                            feedback_failed += failed
                        elif args.feedback_control_lease_ack_window_events > 0:
                            sent, failed = maybe_queue_control_lease_ack(
                                args,
                                feedback_record,
                                pending=control_lease_ack_window,
                                seen=immediate_ack_seen,
                                feedback_client=feedback_client,
                            )
                            feedback_sent += sent
                            feedback_failed += failed
                    if should_send_feedback(args, packets):
                        ack_keys = (
                            control_lease_ack_keys_from_feedback_windows(feedback_windows)
                            if adaptive_ack_pacer is not None
                            else set()
                        )
                        sent, failed = flush_feedback_windows(
                            args,
                            feedback_windows,
                            feedback_client=feedback_client,
                        )
                        if adaptive_ack_pacer is not None and failed == 0:
                            adaptive_ack_pacer.mark_delivered(ack_keys)
                        feedback_sent += sent
                        feedback_failed += failed

                for publication in router.route(event):
                    publisher_key = (publication.topic, publication.msg_type)
                    publisher = publishers.get(publisher_key)
                    if publisher is None:
                        message_type = message_type_for_publication(
                            publication=publication,
                            string_cls=String,
                            twist_cls=Twist,
                            odom_cls=Odometry,
                            scan_cls=LaserScan,
                            projection_quality_cls=ProjectionQualityMsg,
                            qualified_odom_cls=QualifiedOdometry,
                            qualified_scan_cls=QualifiedLaserScan,
                        )
                        publisher = node.create_publisher(message_type, publication.topic, 10)
                        publishers[publisher_key] = publisher
                    publisher.publish(
                        message_for_publication(
                            publication=publication,
                            string_cls=String,
                            twist_cls=Twist,
                            odom_cls=Odometry,
                            scan_cls=LaserScan,
                            projection_quality_cls=ProjectionQualityMsg,
                            qualified_odom_cls=QualifiedOdometry,
                            qualified_scan_cls=QualifiedLaserScan,
                        )
                    )
                    rclpy.spin_once(node, timeout_sec=0.0)
                    handle.write(
                        json.dumps(
                            publication_log_record(
                                publication=publication,
                                recv_monotonic_ns=recv_ns,
                                remote_address=address,
                            ),
                            sort_keys=True,
                        )
                        + "\n"
                    )
                    handle.flush()
                    published += 1
            if args.feedback_sidecar_host:
                if adaptive_ack_pacer is not None:
                    sent, failed = adaptive_ack_pacer.flush(
                        args,
                        feedback_client=feedback_client,
                    )
                else:
                    sent, failed = flush_control_lease_ack_records(
                        args,
                        control_lease_ack_window,
                        feedback_client=feedback_client,
                    )
                feedback_sent += sent
                feedback_failed += failed
                ack_keys = (
                    control_lease_ack_keys_from_feedback_windows(feedback_windows)
                    if adaptive_ack_pacer is not None
                    else set()
                )
                sent, failed = flush_feedback_windows(
                    args,
                    feedback_windows,
                    feedback_client=feedback_client,
                )
                if adaptive_ack_pacer is not None and failed == 0:
                    adaptive_ack_pacer.mark_delivered(ack_keys)
                feedback_sent += sent
                feedback_failed += failed
    finally:
        if feedback_client is not None:
            feedback_client.close()
        node.destroy_node()
        rclpy.shutdown()
        sock.close()
        if forward_sock:
            forward_sock.close()

    print(
        "egress "
        f"received {packets} packets, published {published} messages, "
        f"forwarded {forwarded} packets, invalid {invalid}, "
        f"feedback_sent {feedback_sent}, feedback_failed {feedback_failed}"
    )


def should_send_feedback(args: argparse.Namespace, packets: int) -> bool:
    every = max(1, int(args.feedback_every_packets))
    return packets % every == 0


def update_feedback_window(
    windows: dict[str, dict[str, float]],
    record: dict[str, object],
    *,
    ack_nack_record: dict[str, object] | None = None,
) -> None:
    robot_id = str(record.get("robot_id", ""))
    if not robot_id:
        return
    window = windows.setdefault(
        robot_id,
        {
            "deadline_total": 0.0,
            "deadline_miss": 0.0,
            "control_total": 0.0,
            "control_delivered": 0.0,
            "latency_total_ms": 0.0,
            "latency_tail_ms": 0.0,
            "latency_count": 0.0,
            "latency_deadline_total_ms": 0.0,
            "latency_deadline_count": 0.0,
            "deadline_by_transform": {},
            "_seen_control_lease_event_ids": set(),
            "_ack_nack_records": [],
        },
    )
    flow_class = str(record.get("flow_class", ""))
    if is_duplicate_control_lease_feedback(window, record):
        return
    if ack_nack_record is not None:
        ack_nacks = window.setdefault("_ack_nack_records", [])
        if isinstance(ack_nacks, list):
            ack_nacks.append(dict(ack_nack_record))
    if (
        flow_class in FEEDBACK_DEADLINE_CLASSES
        and "deadline_met" in record
        and not is_control_lease_feedback(record)
    ):
        window["deadline_total"] += 1.0
        transform_key = feedback_transform_key(record)
        if transform_key:
            by_transform = window.setdefault("deadline_by_transform", {})
            if isinstance(by_transform, dict):
                bucket = by_transform.setdefault(
                    transform_key,
                    {"deadline_total": 0.0, "deadline_miss": 0.0},
                )
                if isinstance(bucket, dict):
                    bucket["deadline_total"] = float(bucket.get("deadline_total", 0.0)) + 1.0
                    if not bool(record.get("deadline_met")):
                        bucket["deadline_miss"] = float(bucket.get("deadline_miss", 0.0)) + 1.0
        if not bool(record.get("deadline_met")):
            window["deadline_miss"] += 1.0
    if flow_class == "control":
        window["control_total"] += 1.0
        if bool(record.get("control_delivered")):
            window["control_delivered"] += 1.0
    if flow_class in FEEDBACK_LATENCY_CLASSES and "latency_ms" in record:
        latency_ms = feedback_float(record.get("latency_ms"))
        if latency_ms is not None:
            window["latency_total_ms"] += latency_ms
            window["latency_tail_ms"] = max(window["latency_tail_ms"], latency_ms)
            window["latency_count"] += 1.0
            deadline_ms = feedback_float(record.get("deadline_ms"))
            if deadline_ms is not None and deadline_ms > 0.0:
                window["latency_deadline_total_ms"] += deadline_ms
                window["latency_deadline_count"] += 1.0


def flush_feedback_windows(
    args: argparse.Namespace,
    windows: dict[str, dict[str, float]],
    *,
    feedback_client: RobotFeedbackTcpClient | None = None,
) -> tuple[int, int]:
    records = []
    for robot_id, window in sorted(windows.items()):
        ack_nack_records = [
            dict(item)
            for item in window.get("_ack_nack_records", [])
            if isinstance(item, dict)
        ]
        record: dict[str, object] = {
            "schema_version": "fleetrmw.robot_feedback.v1",
            "source": "egress",
            "robot_id": robot_id,
        }
        control_total = window.get("control_total", 0.0)
        deadline_total = window.get("deadline_total", 0.0)
        latency_count = window.get("latency_count", 0.0)
        if control_total > 0:
            record["control_delivery_ratio"] = (
                window.get("control_delivered", 0.0) / control_total
            )
            record["control_sample_count"] = int(control_total)
            seen_control_ids = window.get("_seen_control_lease_event_ids")
            if isinstance(seen_control_ids, set) and seen_control_ids:
                record["control_lease_event_ids"] = sorted(
                    int(item)
                    for item in seen_control_ids
                    if item is not None
                )
        if deadline_total > 0:
            record["deadline_miss_ratio"] = (
                window.get("deadline_miss", 0.0) / deadline_total
            )
            record["deadline_sample_count"] = int(deadline_total)
            by_transform = window.get("deadline_by_transform")
            if isinstance(by_transform, dict):
                ratios: dict[str, float] = {}
                counts: dict[str, int] = {}
                for key, bucket in sorted(by_transform.items()):
                    if not isinstance(bucket, dict):
                        continue
                    total = float(bucket.get("deadline_total", 0.0))
                    if total <= 0.0:
                        continue
                    ratios[str(key)] = float(bucket.get("deadline_miss", 0.0)) / total
                    counts[str(key)] = int(total)
                if ratios:
                    record["deadline_miss_by_transform"] = ratios
                    record["deadline_sample_count_by_transform"] = counts
        if latency_count > 0:
            mean_latency_ms = window.get("latency_total_ms", 0.0) / latency_count
            tail_latency_ms = window.get("latency_tail_ms", 0.0)
            record["mean_latency_ms"] = mean_latency_ms
            record["tail_latency_ms"] = tail_latency_ms
            record["latency_sample_count"] = int(latency_count)
            deadline_count = window.get("latency_deadline_count", 0.0)
            if deadline_count > 0:
                mean_deadline_ms = (
                    window.get("latency_deadline_total_ms", 0.0) / deadline_count
                )
                record["mean_deadline_ms"] = mean_deadline_ms
                if mean_deadline_ms > 0.0:
                    record["latency_deadline_ratio"] = (
                        tail_latency_ms / mean_deadline_ms
                    )
        sample_count = max(control_total, deadline_total, latency_count)
        if sample_count > 0:
            record["feedback_sample_count"] = int(sample_count)
        if len(record) > 1:
            records.append(record)
        records.extend(ack_nack_records)
    windows.clear()
    if not records:
        return 0, 0
    try:
        if feedback_client is not None:
            response = feedback_client.send_feedback(records)
        else:
            response = send_robot_feedback(
                host=args.feedback_sidecar_host,
                port=args.feedback_sidecar_port,
                records=records,
                timeout_s=args.feedback_timeout_s,
            )
        return int(response.get("applied", 0)), 0
    except (OSError, TimeoutError, json.JSONDecodeError):
        return 0, 1


def control_lease_ack_keys_from_feedback_windows(
    windows: dict[str, dict[str, float]],
) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for robot_id, window in windows.items():
        event_ids = window.get("_seen_control_lease_event_ids")
        if not isinstance(event_ids, set):
            continue
        for event_id in event_ids:
            try:
                keys.add((str(robot_id), int(event_id)))
            except (TypeError, ValueError):
                continue
    return keys


class ControlLeaseAckPacer:
    """Backpressured ACK batcher for control-lease retransmit feedback."""

    def __init__(
        self,
        *,
        min_window_events: int = 8,
        max_window_events: int = 48,
        success_step: int = 1,
        failure_multiplier: float = 2.0,
        max_age_ms: float = 120.0,
        piggyback_first: bool = True,
    ) -> None:
        self.min_window_events = max(1, int(min_window_events))
        self.max_window_events = max(self.min_window_events, int(max_window_events))
        self.success_step = max(0, int(success_step))
        self.failure_multiplier = max(1.0, float(failure_multiplier))
        self.max_age_ms = max(0.0, float(max_age_ms))
        self.piggyback_first = bool(piggyback_first)
        self.current_window_events = self.min_window_events
        self.pending: list[dict[str, object]] = []
        self._pending_keys: set[tuple[str, int]] = set()
        self._delivered_keys: set[tuple[str, int]] = set()
        self._delivered_order: list[tuple[str, int]] = []
        self._delivered_limit = max(2048, self.max_window_events * 32)
        self._batch_sequence = 0
        self._pending_started_ns: int | None = None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "ControlLeaseAckPacer":
        return cls(
            min_window_events=args.feedback_control_lease_ack_adaptive_min_events,
            max_window_events=args.feedback_control_lease_ack_adaptive_max_events,
            success_step=args.feedback_control_lease_ack_adaptive_success_step,
            failure_multiplier=args.feedback_control_lease_ack_adaptive_failure_multiplier,
            max_age_ms=args.feedback_control_lease_ack_adaptive_max_age_ms,
            piggyback_first=args.feedback_control_lease_ack_adaptive_piggyback_first,
        )

    def maybe_ack(
        self,
        args: argparse.Namespace,
        record: dict[str, object],
        *,
        feedback_client: RobotFeedbackTcpClient | None = None,
        now_monotonic_ns: int | None = None,
    ) -> tuple[int, int]:
        now_ns = time.monotonic_ns() if now_monotonic_ns is None else int(now_monotonic_ns)
        ack = immediate_control_lease_ack_record(record)
        if ack is None:
            return 0, 0
        key = control_lease_ack_key(ack)
        if key is None or key in self._pending_keys or key in self._delivered_keys:
            return 0, 0
        self.pending.append(ack)
        self._pending_keys.add(key)
        if self._pending_started_ns is None:
            self._pending_started_ns = now_ns
        if len(self.pending) < self._event_flush_threshold() and not self._pending_age_due(now_ns):
            return 0, 0
        return self.flush(
            args,
            feedback_client=feedback_client,
            now_monotonic_ns=now_ns,
        )

    def flush_if_due(
        self,
        args: argparse.Namespace,
        *,
        feedback_client: RobotFeedbackTcpClient | None = None,
        now_monotonic_ns: int | None = None,
    ) -> tuple[int, int]:
        now_ns = time.monotonic_ns() if now_monotonic_ns is None else int(now_monotonic_ns)
        if not self._pending_age_due(now_ns):
            return 0, 0
        return self.flush(
            args,
            feedback_client=feedback_client,
            now_monotonic_ns=now_ns,
        )

    def flush(
        self,
        args: argparse.Namespace,
        *,
        feedback_client: RobotFeedbackTcpClient | None = None,
        now_monotonic_ns: int | None = None,
    ) -> tuple[int, int]:
        if not self.pending:
            return 0, 0
        now_ns = time.monotonic_ns() if now_monotonic_ns is None else int(now_monotonic_ns)
        batch_id = f"ackb-{self._batch_sequence:08d}"
        self._batch_sequence += 1
        batch = [
            self._record_with_batch_metadata(
                record,
                batch_id=batch_id,
                batch_size=len(self.pending),
            )
            for record in self.pending
        ]
        sent, failed = send_control_lease_ack_batch(
            args,
            batch,
            feedback_client=feedback_client,
        )
        if failed:
            self._pending_started_ns = now_ns
            self.current_window_events = min(
                self.max_window_events,
                max(
                    self.current_window_events + 1,
                    int(math.ceil(self.current_window_events * self.failure_multiplier)),
                ),
            )
            return sent, failed
        self._mark_delivered(self._pending_keys)
        self.pending.clear()
        self._pending_keys.clear()
        self._pending_started_ns = None
        self.current_window_events = max(
            self.min_window_events,
            self.current_window_events - self.success_step,
        )
        return sent, 0

    def mark_delivered(self, keys: set[tuple[str, int]]) -> None:
        if not keys:
            return
        self._mark_delivered(keys)
        if not self._pending_keys.intersection(keys):
            return
        self.pending = [
            record
            for record in self.pending
            if control_lease_ack_key(record) not in keys
        ]
        self._pending_keys.difference_update(keys)
        if not self.pending:
            self._pending_started_ns = None

    def _event_flush_threshold(self) -> int:
        if self.piggyback_first:
            return self.max_window_events
        return self.current_window_events

    def _pending_age_due(self, now_ns: int) -> bool:
        if not self.pending or self._pending_started_ns is None or self.max_age_ms <= 0.0:
            return False
        backpressure_scale = self.current_window_events / self.min_window_events
        max_age_ns = int(self.max_age_ms * backpressure_scale * 1_000_000)
        return now_ns - self._pending_started_ns >= max_age_ns

    def _record_with_batch_metadata(
        self,
        record: dict[str, object],
        *,
        batch_id: str,
        batch_size: int,
    ) -> dict[str, object]:
        enriched = dict(record)
        enriched["ack_pacing_mode"] = "adaptive_window"
        enriched["ack_batch_id"] = batch_id
        enriched["ack_batch_size"] = int(batch_size)
        enriched["ack_window_events"] = int(self.current_window_events)
        return enriched

    def _mark_delivered(self, keys: set[tuple[str, int]]) -> None:
        for key in sorted(keys):
            if key in self._delivered_keys:
                continue
            self._delivered_keys.add(key)
            self._delivered_order.append(key)
        while len(self._delivered_order) > self._delivered_limit:
            old = self._delivered_order.pop(0)
            self._delivered_keys.discard(old)


def maybe_send_immediate_control_lease_ack(
    args: argparse.Namespace,
    record: dict[str, object],
    *,
    seen: set[tuple[str, int]],
    feedback_client: RobotFeedbackTcpClient | None = None,
) -> tuple[int, int]:
    ack = immediate_control_lease_ack_record(record)
    if ack is None:
        return 0, 0
    key = control_lease_ack_key(ack)
    if key is None:
        return 0, 0
    if key in seen:
        return 0, 0
    seen.add(key)
    return flush_control_lease_ack_records(
        args,
        [ack],
        feedback_client=feedback_client,
    )


def maybe_queue_control_lease_ack(
    args: argparse.Namespace,
    record: dict[str, object],
    *,
    pending: list[dict[str, object]],
    seen: set[tuple[str, int]],
    feedback_client: RobotFeedbackTcpClient | None = None,
) -> tuple[int, int]:
    ack = immediate_control_lease_ack_record(record)
    if ack is None:
        return 0, 0
    key = control_lease_ack_key(ack)
    if key is None:
        return 0, 0
    if key in seen:
        return 0, 0
    seen.add(key)
    pending.append(ack)
    window_events = max(1, int(args.feedback_control_lease_ack_window_events))
    if len(pending) < window_events:
        return 0, 0
    return flush_control_lease_ack_records(
        args,
        pending,
        feedback_client=feedback_client,
    )


def flush_control_lease_ack_records(
    args: argparse.Namespace,
    records: list[dict[str, object]],
    *,
    feedback_client: RobotFeedbackTcpClient | None = None,
) -> tuple[int, int]:
    if not records:
        return 0, 0
    batch = list(records)
    records.clear()
    return send_control_lease_ack_batch(
        args,
        batch,
        feedback_client=feedback_client,
    )


def send_control_lease_ack_batch(
    args: argparse.Namespace,
    batch: list[dict[str, object]],
    *,
    feedback_client: RobotFeedbackTcpClient | None = None,
) -> tuple[int, int]:
    if not batch:
        return 0, 0
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
        ack_result = response.get("control_lease_ack", {})
        if isinstance(ack_result, dict):
            return int(ack_result.get("ack_feedback_records", len(batch))), 0
        return len(batch), 0
    except (OSError, TimeoutError, json.JSONDecodeError):
        return 0, 1


def control_lease_ack_key(ack: dict[str, object]) -> tuple[str, int] | None:
    robot_id = str(ack.get("robot_id", ""))
    event_ids = ack.get("control_lease_event_ids")
    if not robot_id or not isinstance(event_ids, list) or not event_ids:
        return None
    try:
        return robot_id, int(event_ids[0])
    except (TypeError, ValueError):
        return None


def immediate_control_lease_ack_record(
    record: dict[str, object],
) -> dict[str, object] | None:
    if not is_control_lease_feedback(record):
        return None
    robot_id = str(record.get("robot_id", ""))
    event_id = record.get("event_id")
    if not robot_id or event_id is None:
        return None
    try:
        event_id_int = int(event_id)
    except (TypeError, ValueError):
        return None
    ack: dict[str, object] = {
        "schema_version": "fleetrmw.robot_feedback.v1",
        "source": "egress_ack",
        "robot_id": robot_id,
        "control_lease_event_ids": [event_id_int],
        "feedback_sample_count": 1,
    }
    flow_id = record.get("flow_id")
    if flow_id:
        ack["flow_id"] = str(flow_id)
    source_topic = record.get("source_topic")
    if source_topic:
        ack["source_topic"] = str(source_topic)
    for key in (
        "source_sample_id",
        "source_sequence_number",
        "source_timestamp_ns",
        "source_received_timestamp_ns",
    ):
        value = record.get(key)
        if value is not None:
            ack[key] = value
    return ack


def feedback_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def feedback_transform_key(record: dict[str, object]) -> str:
    flow_class = str(record.get("flow_class", "")).strip().lower()
    wire_mode = str(record.get("wire_mode", "") or record.get("action", "")).strip().lower()
    if not wire_mode:
        return ""
    return f"{flow_class}:{wire_mode}" if flow_class else wire_mode


def is_control_lease_feedback(record: dict[str, object]) -> bool:
    if str(record.get("flow_class", "")).strip().lower() != "control":
        return False
    action = str(record.get("action", "")).strip().lower()
    wire_mode = str(record.get("wire_mode", "")).strip().lower()
    return action in {"send_intent", "send_supervisory_intent"} or wire_mode in {
        "control_intent",
        "supervisory_intent",
    }


def is_duplicate_control_lease_feedback(
    window: dict[str, object],
    record: dict[str, object],
) -> bool:
    if not is_control_lease_feedback(record):
        return False
    event_id = record.get("event_id")
    if event_id is None:
        return False
    seen = window.setdefault("_seen_control_lease_event_ids", set())
    if not isinstance(seen, set):
        return False
    if event_id in seen:
        return True
    seen.add(event_id)
    return False


def publication_log_record(
    *,
    publication: EgressPublication,
    recv_monotonic_ns: int,
    remote_address: tuple[str, int],
) -> dict[str, object]:
    record = publication.as_log_record()
    record["recv_monotonic_ns"] = recv_monotonic_ns
    record["remote_host"] = remote_address[0]
    record["remote_port"] = remote_address[1]
    return record


def message_type_for_publication(
    *,
    publication: EgressPublication,
    string_cls,
    twist_cls,
    odom_cls,
    scan_cls,
    projection_quality_cls,
    qualified_odom_cls,
    qualified_scan_cls,
):
    if publication.msg_type == "std_msgs/msg/String":
        return string_cls
    if publication.msg_type == FLEETRMW_PROJECTION_QUALITY_MSG_TYPE:
        if projection_quality_cls is None:
            raise ValueError("fleetrmw_interfaces ProjectionQuality class is not available")
        return projection_quality_cls
    if publication.msg_type == FLEETRMW_QUALIFIED_ODOMETRY_MSG_TYPE:
        if qualified_odom_cls is None:
            raise ValueError("fleetrmw_interfaces QualifiedOdometry class is not available")
        return qualified_odom_cls
    if publication.msg_type == FLEETRMW_QUALIFIED_LASER_SCAN_MSG_TYPE:
        if qualified_scan_cls is None:
            raise ValueError("fleetrmw_interfaces QualifiedLaserScan class is not available")
        return qualified_scan_cls
    if publication.msg_type == "geometry_msgs/msg/Twist":
        return twist_cls
    if publication.msg_type == "nav_msgs/msg/Odometry":
        return odom_cls
    if publication.msg_type == "sensor_msgs/msg/LaserScan":
        return scan_cls
    raise ValueError(f"unsupported egress msg_type: {publication.msg_type}")


def message_for_publication(
    *,
    publication: EgressPublication,
    string_cls,
    twist_cls,
    odom_cls,
    scan_cls,
    projection_quality_cls,
    qualified_odom_cls,
    qualified_scan_cls,
):
    if publication.msg_type == "std_msgs/msg/String":
        return string_cls(data=publication.payload)
    if publication.msg_type == FLEETRMW_PROJECTION_QUALITY_MSG_TYPE:
        if projection_quality_cls is None:
            raise ValueError("fleetrmw_interfaces ProjectionQuality class is not available")
        return projection_quality_message_from_payload(projection_quality_cls, json.loads(publication.payload))
    if publication.msg_type == FLEETRMW_QUALIFIED_ODOMETRY_MSG_TYPE:
        if qualified_odom_cls is None:
            raise ValueError("fleetrmw_interfaces QualifiedOdometry class is not available")
        payload = json.loads(publication.payload)
        message = qualified_odom_cls()
        assign_projection_quality_message(message.quality, _mapping(payload.get("quality", {})))
        _assign_odometry_message(message.sample, _mapping(payload.get("sample", {})))
        return message
    if publication.msg_type == FLEETRMW_QUALIFIED_LASER_SCAN_MSG_TYPE:
        if qualified_scan_cls is None:
            raise ValueError("fleetrmw_interfaces QualifiedLaserScan class is not available")
        payload = json.loads(publication.payload)
        message = qualified_scan_cls()
        assign_projection_quality_message(message.quality, _mapping(payload.get("quality", {})))
        _assign_laser_scan_message(message.sample, _mapping(payload.get("sample", {})))
        return message
    if publication.msg_type == "geometry_msgs/msg/Twist":
        payload = json.loads(publication.payload)
        twist = payload.get("twist", {})
        message = twist_cls()
        _assign_vector(message.linear, twist.get("linear", {}))
        _assign_vector(message.angular, twist.get("angular", {}))
        return message
    if publication.msg_type == "nav_msgs/msg/Odometry":
        payload = json.loads(publication.payload)
        message = odom_cls()
        _assign_odometry_message(message, payload)
        return message
    if publication.msg_type == "sensor_msgs/msg/LaserScan":
        payload = json.loads(publication.payload)
        message = scan_cls()
        _assign_laser_scan_message(message, payload)
        return message
    raise ValueError(f"unsupported egress msg_type: {publication.msg_type}")


def _assign_header(header, payload: object) -> None:
    data = _mapping(payload)
    stamp = _mapping(data.get("stamp"))
    header.stamp.sec = _int_value(stamp.get("sec"))
    header.stamp.nanosec = _int_value(stamp.get("nanosec"))
    header.frame_id = str(data.get("frame_id", ""))


def _assign_odometry_message(message, payload: object) -> None:
    data = _mapping(payload)
    odom = _mapping(data.get("odometry", {}))
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


def _assign_laser_scan_message(message, payload: object) -> None:
    data = _mapping(payload)
    scan = _mapping(data.get("scan", {}))
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


def _assign_vector(vector, payload: object) -> None:
    data = payload if isinstance(payload, dict) else {}
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
    return value if isinstance(value, dict) else {}


def _sequence(value: object) -> list:
    return value if isinstance(value, list) else []


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
