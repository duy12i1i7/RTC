"""Minimal FleetRMW publish/take boundary.

The real ``rmw_fleetqox_cpp`` implementation will live below ``rcl``.  This
module is a dependency-free executable contract for that boundary: a ROS-like
sample is assigned native FleetRMW source identity, admitted into a data frame,
and a receiver produces source-sequence ACK/NACK feedback after taking frames.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from .model import NetworkLink
from .rmw_ack import RmwAckNackTracker
from .rmw_contract import (
    FleetRmwSampleEnvelope,
    publisher_id_for_fields,
    sample_envelope_for_fields,
)
from .rmw_frame import (
    data_frame_from_sidecar_event,
    decode_data_frame,
    encode_data_frame,
    sidecar_event_from_data_frame,
)
from .ros2_shim import Ros2Sample, Ros2SidecarAdapter
from .sidecar_runtime import build_sidecar_event, policy_from_name


RMW_BOUNDARY_PUBLISH_SCHEMA_VERSION = "fleetrmw.rmw_publish.v1"
RMW_BOUNDARY_TAKE_SCHEMA_VERSION = "fleetrmw.rmw_take.v1"
DEFAULT_RMW_IMPLEMENTATION = "rmw_fleetqox_boundary"


@dataclass(frozen=True)
class FleetRmwBoundaryConfig:
    scenario: str = "fleetrmw_boundary_smoke"
    policy: str = "fleetqox_semantic_contract_adaptive"
    link: NetworkLink = NetworkLink(capacity_bytes_per_tick=4096)
    packet_target_size: int | None = None
    rmw_implementation: str = DEFAULT_RMW_IMPLEMENTATION


class FleetRmwBoundary:
    """In-memory FleetRMW boundary for tests, replay, and future RMW contracts."""

    def __init__(
        self,
        config: FleetRmwBoundaryConfig | None = None,
        *,
        adapter: Ros2SidecarAdapter | None = None,
        ack_tracker: RmwAckNackTracker | None = None,
    ) -> None:
        self.config = config or FleetRmwBoundaryConfig()
        self.adapter = adapter or Ros2SidecarAdapter()
        self.ack_tracker = ack_tracker or RmwAckNackTracker()
        self._policy = policy_from_name(self.config.policy)
        self._event_id = 0
        self._source_sequences: dict[tuple[str, str, str, str], int] = {}

    def publish(
        self,
        sample: Ros2Sample | Mapping[str, object],
        *,
        timestamp_ms: float,
        tick: int,
        link: NetworkLink | None = None,
    ) -> dict[str, object]:
        """Admit one ROS-like sample and return its FleetRMW data frame."""

        base_sample = sample if isinstance(sample, Ros2Sample) else Ros2Sample.from_payload(sample)
        effective_link = link or self.config.link
        native_sample = self._with_native_envelope(base_sample, timestamp_ms=timestamp_ms)
        flow = self.adapter.flow_spec_for_sample(native_sample)
        observation = self.adapter.observation_for_sample(native_sample, flow, effective_link)
        decisions = self._policy([(flow, observation)], effective_link)
        if not decisions:
            raise RuntimeError("FleetRMW boundary policy returned no decision")
        event = build_sidecar_event(
            event_id=self._next_event_id(),
            scenario=self.config.scenario,
            policy=self.config.policy,
            timestamp_ms=timestamp_ms,
            tick=tick,
            flow=flow,
            obs=observation,
            link=effective_link,
            decision=decisions[0],
            contract_id=native_sample.contract_id,
            source_sample_id=native_sample.source_sample_id,
            source_metadata=source_metadata_payload(native_sample),
            sample_envelope=native_sample.sample_envelope.as_payload()
            if native_sample.sample_envelope
            else None,
            semantic_payload=native_sample.semantic_payload,
        )
        frame = data_frame_from_sidecar_event(event)
        encoded = encode_data_frame(
            frame,
            target_size=(
                self.config.packet_target_size
                if self.config.packet_target_size is not None
                else _positive_int(event.get("bytes"))
            ),
        )
        return {
            "schema_version": RMW_BOUNDARY_PUBLISH_SCHEMA_VERSION,
            "status": "published",
            "event": event,
            "frame": frame,
            "encoded": encoded,
            "sample_envelope": native_sample.sample_envelope.as_payload()
            if native_sample.sample_envelope
            else None,
        }

    def take(self, payload: bytes | Mapping[str, object]) -> dict[str, object]:
        """Take one FleetRMW data frame and emit source-sequence ACK/NACK."""

        if isinstance(payload, bytes):
            frame = decode_data_frame(payload)
            if frame is None:
                return {
                    "schema_version": RMW_BOUNDARY_TAKE_SCHEMA_VERSION,
                    "status": "ignored",
                    "reason": "not_fleetrmw_data_frame",
                }
        else:
            frame = dict(payload)
        event = sidecar_event_from_data_frame(frame)
        ack_nack = self.ack_tracker.observe(event)
        return {
            "schema_version": RMW_BOUNDARY_TAKE_SCHEMA_VERSION,
            "status": "taken",
            "frame_id": frame.get("frame_id"),
            "event": event,
            "local_sample": local_sample_payload(event),
            "ack_nack": ack_nack,
        }

    def _with_native_envelope(self, sample: Ros2Sample, *, timestamp_ms: float) -> Ros2Sample:
        initial_flow = self.adapter.flow_spec_for_sample(sample)
        if sample.sample_envelope is not None:
            envelope = sample.sample_envelope
        else:
            sequence = (
                sample.sequence_number
                if sample.sequence_number is not None
                else self._allocate_source_sequence(
                    robot_id=initial_flow.robot_id,
                    topic=sample.topic,
                    msg_type=sample.msg_type,
                    node_name=sample.node_name,
                    publisher_gid=sample.publisher_gid,
                )
            )
            timestamp_ns = (
                sample.source_timestamp_ns
                if sample.source_timestamp_ns is not None
                else int(timestamp_ms * 1_000_000)
            )
            received_timestamp_ns = (
                sample.received_timestamp_ns
                if sample.received_timestamp_ns is not None
                else timestamp_ns
            )
            publisher_id = publisher_id_for_fields(
                robot_id=initial_flow.robot_id,
                topic=sample.topic,
                msg_type=sample.msg_type,
                node_name=sample.node_name,
                publisher_gid=sample.publisher_gid,
                rmw_implementation=self.config.rmw_implementation,
            )
            envelope = sample_envelope_for_fields(
                robot_id=initial_flow.robot_id,
                topic=sample.topic,
                msg_type=sample.msg_type,
                publisher_id=publisher_id,
                source_sample_id=sample.source_sample_id,
                source_sequence_number=sequence,
                source_timestamp_ns=timestamp_ns,
                received_timestamp_ns=received_timestamp_ns,
                publisher_gid=sample.publisher_gid,
                node_name=sample.node_name,
                rmw_implementation=self.config.rmw_implementation,
            )
        return replace(
            sample,
            robot_id=sample.robot_id or envelope.robot_id,
            source_sample_id=sample.source_sample_id or envelope.source_sample_id,
            sequence_number=(
                sample.sequence_number
                if sample.sequence_number is not None
                else envelope.source_sequence_number
            ),
            source_timestamp_ns=(
                sample.source_timestamp_ns
                if sample.source_timestamp_ns is not None
                else envelope.source_timestamp_ns
            ),
            received_timestamp_ns=(
                sample.received_timestamp_ns
                if sample.received_timestamp_ns is not None
                else envelope.received_timestamp_ns
            ),
            sample_envelope=envelope,
        )

    def _allocate_source_sequence(
        self,
        *,
        robot_id: str,
        topic: str,
        msg_type: str,
        node_name: str,
        publisher_gid: str | None,
    ) -> int:
        key = (
            robot_id,
            topic,
            msg_type,
            publisher_gid or node_name or self.config.rmw_implementation,
        )
        sequence = self._source_sequences.get(key, 0) + 1
        self._source_sequences[key] = sequence
        return sequence

    def _next_event_id(self) -> int:
        event_id = self._event_id
        self._event_id += 1
        return event_id


def source_metadata_payload(sample: Ros2Sample) -> dict[str, object]:
    if sample.sample_envelope is not None:
        return sample.sample_envelope.source_metadata_payload()
    return {}


def local_sample_payload(event: Mapping[str, object]) -> dict[str, object]:
    semantic_payload = event.get("semantic_payload")
    if isinstance(semantic_payload, Mapping):
        return dict(semantic_payload)
    sample_envelope = event.get("sample_envelope")
    if isinstance(sample_envelope, Mapping):
        return {"sample_envelope": dict(sample_envelope)}
    return {}


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
