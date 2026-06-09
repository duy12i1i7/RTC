"""Persistent FleetRMW socket transport loop.

This module keeps one talker/listener pair alive while publishing many source
streams, observing ACK/NACK feedback, and replaying missing source sequences.
It is the executable transport contract between the Python sidecar prototype and
the future ``rmw_fleetqox_cpp`` implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
import socket
from typing import Iterable, Mapping

from .rmw_socket import (
    FleetRmwSocketConfig,
    FleetRmwSocketListener,
    FleetRmwSocketTalker,
)
from .ros2_shim import Ros2Sample


RMW_TRANSPORT_LOOP_SCHEMA_VERSION = "fleetrmw.rmw_transport_loop.v1"


@dataclass(frozen=True)
class FleetRmwSocketLoopConfig:
    robot_count: int = 2
    samples_per_robot: int = 3
    skip_every: int = 0
    late_skipped: bool = True
    timeout_s: float = 1.0
    recovery_horizon_ms: float = 2000.0
    history_per_stream: int = 256


class FleetRmwSocketTransportLoop:
    """Run a deterministic multi-stream FleetRMW socket transport loop."""

    def __init__(self, config: FleetRmwSocketLoopConfig | None = None) -> None:
        self.config = config or FleetRmwSocketLoopConfig()

    def run(
        self,
        *,
        skip_initial: Iterable[tuple[str, int]] | None = None,
    ) -> dict[str, object]:
        skipped = self._skip_set(skip_initial)
        feedback_records: list[dict[str, object]] = []
        retransmit_records: list[dict[str, object]] = []
        published = 0
        taken = 0
        with FleetRmwSocketListener(self._socket_config()) as listener:
            with FleetRmwSocketTalker(self._socket_config()) as talker:
                for robot_index in range(max(0, self.config.robot_count)):
                    robot_id = f"robot_{robot_index:04d}"
                    for sequence in range(1, max(0, self.config.samples_per_robot) + 1):
                        sample = socket_loop_sample(robot_id, sequence)
                        destination = (
                            ("127.0.0.1", _unused_udp_port())
                            if (robot_id, sequence) in skipped
                            else listener.address
                        )
                        published += 1
                        talker.publish(
                            sample,
                            timestamp_ms=float(sequence * 20),
                            tick=sequence,
                            destination=destination,
                        )
                        if destination != listener.address:
                            continue
                        delivered, retransmitted = self._drain_one_delivery(
                            talker=talker,
                            listener=listener,
                            feedback_records=feedback_records,
                            retransmit_records=retransmit_records,
                        )
                        taken += delivered
        return self._summary(
            skipped=skipped,
            feedback_records=feedback_records,
            retransmit_records=retransmit_records,
            published=published,
            taken=taken,
        )

    def _drain_one_delivery(
        self,
        *,
        talker: FleetRmwSocketTalker,
        listener: FleetRmwSocketListener,
        feedback_records: list[dict[str, object]],
        retransmit_records: list[dict[str, object]],
    ) -> tuple[int, int]:
        received = listener.receive_once(timeout_s=self.config.timeout_s)
        feedback = talker.receive_feedback(timeout_s=self.config.timeout_s)
        if received is None or feedback is None:
            raise RuntimeError("FleetRMW transport loop did not complete a feedback round trip")
        feedback_records.append(feedback["feedback"])
        taken = 1 if received.get("status") == "taken" else 0
        retransmitted = 0
        if not self.config.late_skipped:
            return taken, retransmitted
        while True:
            retransmit = talker.retransmit_from_feedback(
                feedback["feedback"],
                destination=listener.address,
            )
            sequences = retransmit.get("retransmitted_sequences", [])
            if not sequences:
                break
            retransmit_records.append(retransmit)
            for _sequence in sequences:
                late_received = listener.receive_once(timeout_s=self.config.timeout_s)
                late_feedback = talker.receive_feedback(timeout_s=self.config.timeout_s)
                if late_received is None or late_feedback is None:
                    raise RuntimeError("FleetRMW transport loop did not complete a retransmit round trip")
                taken += 1 if late_received.get("status") == "taken" else 0
                retransmitted += 1
                feedback = late_feedback
                feedback_records.append(late_feedback["feedback"])
        return taken, retransmitted

    def _summary(
        self,
        *,
        skipped: set[tuple[str, int]],
        feedback_records: list[dict[str, object]],
        retransmit_records: list[dict[str, object]],
        published: int,
        taken: int,
    ) -> dict[str, object]:
        gaps = [
            feedback
            for feedback in feedback_records
            if feedback.get("nack", {}).get("missing_sequence_ranges")
        ]
        retransmitted = sum(
            len(record.get("retransmitted_sequences", []))
            for record in retransmit_records
        )
        return {
            "schema_version": RMW_TRANSPORT_LOOP_SCHEMA_VERSION,
            "robot_count": self.config.robot_count,
            "samples_per_robot": self.config.samples_per_robot,
            "skip_every": self.config.skip_every,
            "published": published,
            "taken": taken,
            "retransmitted": retransmitted,
            "ack_nack_feedback": len(feedback_records),
            "missing_sequence_range_count": sum(
                len(feedback.get("nack", {}).get("missing_sequence_ranges", []))
                for feedback in feedback_records
            ),
            "late_out_of_order_count": sum(
                1
                for feedback in feedback_records
                if feedback.get("state", {}).get("out_of_order")
            ),
            "streams_with_gaps": sorted(
                "/".join(str(part) for part in feedback.get("stream_key", []))
                for feedback in gaps
            ),
            "initial_skips": sorted(f"{robot_id}:{sequence}" for robot_id, sequence in skipped),
            "late_skipped": bool(self.config.late_skipped),
            "retransmit_records": retransmit_records,
        }

    def _skip_set(self, explicit: Iterable[tuple[str, int]] | None) -> set[tuple[str, int]]:
        skipped = set(explicit or set())
        if self.config.skip_every > 0:
            skipped.update(
                (f"robot_{robot_index:04d}", sequence)
                for robot_index in range(max(0, self.config.robot_count))
                for sequence in range(1, max(0, self.config.samples_per_robot) + 1)
                if sequence % self.config.skip_every == 0
            )
        return skipped

    def _socket_config(self) -> FleetRmwSocketConfig:
        return FleetRmwSocketConfig(
            timeout_s=self.config.timeout_s,
            recovery_horizon_ms=self.config.recovery_horizon_ms,
            history_per_stream=self.config.history_per_stream,
        )


def socket_loop_sample(robot_id: str, sequence: int) -> Ros2Sample:
    return Ros2Sample(
        topic=f"/{robot_id}/cmd_vel",
        msg_type="geometry_msgs/msg/Twist",
        robot_id=robot_id,
        sequence_number=sequence,
        source_timestamp_ns=sequence * 1_000_000,
        age_ms=8.0,
        collision_risk=0.8,
        semantic_payload={
            "msg_type": "geometry_msgs/msg/Twist",
            "source_sequence_number": sequence,
            "twist": {
                "linear": {"x": 0.1 * sequence, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.1},
            },
        },
    )


def _unused_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()
