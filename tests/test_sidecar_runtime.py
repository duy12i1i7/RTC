import json
import socket
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fleetqox.model import (
    FlowClass,
    FlowDecision,
    FlowObservation,
    FlowSpec,
    NetworkLink,
    QoEProfile,
    QoSProfile,
    TaskContext,
)
from fleetqox.sidecar_contract import validate_event
from fleetqox.sidecar_egress import decode_sidecar_packet
from fleetqox.sidecar_runtime import (
    RuntimeConfig,
    SIDECAR_POLICIES,
    SidecarRuntime,
    SyntheticBatchStream,
    adaptive_control_lease_redundancy_for_config,
    apply_transport_volatility_guard,
    build_sidecar_event,
    control_lease_redundancy_plan_for_event,
    control_lease_redundancy_for_config,
    generate_synthetic_batches,
    flow_spec_to_payload,
    observation_to_payload,
    lagrangian_config_from_overrides,
    paced_control_lease_redundancy_for_config,
    send_batches,
    serve_tcp,
    transport_volatility_guard_applies,
    transmission_count_for_event,
)
from fleetqox.transport_selector import TransportBinding


class SidecarRuntimeTest(unittest.TestCase):
    def test_supervisory_intent_event_uses_effective_lifespan(self) -> None:
        flow = _runtime_flow(
            flow_class=FlowClass.CONTROL,
            deadline_ms=45.0,
            lifespan_ms=90.0,
        )
        obs = _runtime_obs(flow)
        link = NetworkLink(
            capacity_bytes_per_tick=4096,
            loss=0.03,
            jitter_ms=25.0,
            rtt_ms=160.0,
        )
        decision = FlowDecision(
            flow_id=flow.flow_id,
            action="send_supervisory_intent",
            priority=1.0,
            allocated_bytes=48,
            reason="test",
            reliability="best_effort_fresh",
            wire_mode="supervisory_intent",
            predicted_slack_ms=12.0,
        )

        event = build_sidecar_event(
            event_id=1,
            scenario="test",
            policy="fleetqox_semantic_contract_budgeted_deadline_first",
            timestamp_ms=10.0,
            tick=1,
            flow=flow,
            obs=obs,
            link=link,
            decision=decision,
        )

        self.assertEqual(event["deadline_ms"], 293.75)
        self.assertEqual(event["lifespan_ms"], 293.75)
        self.assertEqual(event["source_lifespan_ms"], 90.0)
        self.assertEqual(event["liveliness_lease_ms"], 500.0)
        validate_event(event)

    def test_native_event_keeps_source_lifespan(self) -> None:
        flow = _runtime_flow(
            flow_class=FlowClass.STATE,
            deadline_ms=100.0,
            lifespan_ms=250.0,
        )
        obs = _runtime_obs(flow)
        link = NetworkLink(capacity_bytes_per_tick=4096)
        decision = FlowDecision(
            flow_id=flow.flow_id,
            action="send",
            priority=1.0,
            allocated_bytes=120,
            reason="test",
            wire_mode="native",
        )

        event = build_sidecar_event(
            event_id=2,
            scenario="test",
            policy="fleetqox_semantic_contract_budgeted_deadline_first",
            timestamp_ms=20.0,
            tick=2,
            flow=flow,
            obs=obs,
            link=link,
            decision=decision,
        )

        self.assertEqual(event["deadline_ms"], 100.0)
        self.assertEqual(event["lifespan_ms"], 250.0)
        self.assertEqual(event["source_lifespan_ms"], 250.0)
        validate_event(event)

    def test_deadline_first_policy_redundantly_transmits_control_leases(self) -> None:
        redundancy = control_lease_redundancy_for_config(
            RuntimeConfig(policy="fleetqox_semantic_contract_budgeted_deadline_first")
        )
        event = {
            "event_type": "packet",
            "flow_class": "control",
            "action": "send_intent",
            "wire_mode": "control_intent",
        }
        state_event = {
            "event_type": "packet",
            "flow_class": "state",
            "action": "send",
            "wire_mode": "native",
        }

        self.assertEqual(redundancy, 2)
        self.assertEqual(transmission_count_for_event(event, redundancy), 2)
        self.assertEqual(transmission_count_for_event(state_event, redundancy), 1)

    def test_deadline_first_policy_adaptively_raises_control_lease_redundancy(self) -> None:
        config = RuntimeConfig(
            policy="fleetqox_semantic_contract_budgeted_deadline_first",
            control_lease_adaptive_redundancy=True,
            control_lease_adaptive_max_redundancy=3,
            control_lease_residual_loss_budget=0.01,
        )
        event = {
            "event_type": "packet",
            "flow_class": "control",
            "action": "send_intent",
            "wire_mode": "control_intent",
            "deadline_ms": 293.75,
            "link_loss": 0.03,
            "link_rtt_ms": 160.0,
            "link_jitter_ms": 25.0,
        }

        plan = control_lease_redundancy_plan_for_event(event, config)

        self.assertTrue(adaptive_control_lease_redundancy_for_config(config))
        self.assertEqual(plan["base"], 2)
        self.assertEqual(plan["count"], 3)
        self.assertTrue(plan["adaptive"])
        self.assertGreater(plan["erasure_probability"], 0.10)

    def test_control_lease_adaptive_redundancy_can_be_disabled(self) -> None:
        config = RuntimeConfig(
            policy="fleetqox_semantic_contract_budgeted_deadline_first",
            control_lease_adaptive_redundancy=False,
        )
        event = {
            "event_type": "packet",
            "flow_class": "control",
            "action": "send_intent",
            "wire_mode": "control_intent",
            "deadline_ms": 293.75,
            "link_loss": 0.03,
            "link_rtt_ms": 160.0,
            "link_jitter_ms": 25.0,
        }

        plan = control_lease_redundancy_plan_for_event(event, config)

        self.assertFalse(adaptive_control_lease_redundancy_for_config(config))
        self.assertEqual(plan["base"], 2)
        self.assertEqual(plan["count"], 2)
        self.assertFalse(plan["adaptive"])

    def test_deadline_first_policy_paces_control_lease_redundancy(self) -> None:
        self.assertTrue(
            paced_control_lease_redundancy_for_config(
                RuntimeConfig(policy="fleetqox_semantic_contract_budgeted_deadline_first")
            )
        )

        class FakeUdp:
            def __init__(self) -> None:
                self.payloads: list[bytes] = []
                self.addrs: list[tuple[str, int]] = []

            def sendto(self, payload: bytes, addr) -> None:
                self.payloads.append(payload)
                self.addrs.append(addr)

            def close(self) -> None:
                pass

        runtime = SidecarRuntime(
            RuntimeConfig(
                policy="fleetqox_semantic_contract_budgeted_deadline_first",
                control_lease_redundancy=2,
                control_lease_paced_redundancy=True,
                control_lease_terminal_replay_interval_s=0.0,
            )
        )
        fake_udp = FakeUdp()
        runtime._udp.close()
        runtime._udp = fake_udp
        event = {
            "event_type": "packet",
            "flow_class": "control",
            "robot_id": "robot_0000",
            "action": "send_intent",
            "wire_mode": "control_intent",
            "bytes": 48,
        }
        try:
            emitted = runtime._emit_event_with_redundancy(event, "event_json")
            self.assertEqual(emitted, 1)
            self.assertEqual(len(fake_udp.payloads), 1)
            self.assertEqual(len(runtime._pending_control_lease_retransmits), 1)

            flushed = runtime._flush_paced_control_lease_retransmits("event_json")
        finally:
            runtime.close()

        self.assertEqual(flushed, 1)
        self.assertEqual(len(fake_udp.payloads), 2)
        retransmit = json.loads(fake_udp.payloads[1].rstrip(b" ").decode("utf-8"))
        self.assertEqual(retransmit["paced_retransmit_attempt"], 1)
        self.assertIn("send_monotonic_ns", retransmit)

    def test_paced_control_lease_redundancy_uses_adaptive_count(self) -> None:
        class FakeUdp:
            def __init__(self) -> None:
                self.payloads: list[bytes] = []

            def sendto(self, payload: bytes, _addr) -> None:
                self.payloads.append(payload)

            def close(self) -> None:
                pass

        runtime = SidecarRuntime(
            RuntimeConfig(
                policy="fleetqox_semantic_contract_budgeted_deadline_first",
                control_lease_paced_redundancy=True,
                control_lease_adaptive_redundancy=True,
                control_lease_adaptive_max_redundancy=3,
            )
        )
        fake_udp = FakeUdp()
        runtime._udp.close()
        runtime._udp = fake_udp
        event = {
            "event_type": "packet",
            "flow_class": "control",
            "action": "send_intent",
            "wire_mode": "control_intent",
            "bytes": 48,
            "deadline_ms": 293.75,
            "link_loss": 0.03,
            "link_rtt_ms": 160.0,
            "link_jitter_ms": 25.0,
            "reason": "base",
        }
        try:
            annotated = runtime._annotate_control_lease_redundancy(event)
            emitted = runtime._emit_event_with_redundancy(annotated, "event_json")
            self.assertEqual(emitted, 1)
            self.assertEqual(len(runtime._pending_control_lease_retransmits), 2)

            flushed = runtime._flush_paced_control_lease_retransmits("event_json")
            self.assertEqual(flushed, 1)
            self.assertEqual(len(runtime._pending_control_lease_retransmits), 1)
            flushed += runtime._flush_paced_control_lease_retransmits("event_json")
        finally:
            runtime.close()

        self.assertEqual(flushed, 2)
        self.assertEqual(len(fake_udp.payloads), 3)
        attempts = [
            json.loads(payload.rstrip(b" ").decode("utf-8")).get(
                "paced_retransmit_attempt",
                0,
            )
            for payload in fake_udp.payloads
        ]
        self.assertEqual(attempts, [0, 1, 2])
        first = json.loads(fake_udp.payloads[0].rstrip(b" ").decode("utf-8"))
        self.assertEqual(first["control_lease_redundancy"], 3)
        self.assertIn("control_lease_adaptive_redundancy=3x", first["reason"])

    def test_adaptive_control_lease_extra_copies_are_quota_limited_per_tick(self) -> None:
        runtime = SidecarRuntime(
            RuntimeConfig(
                policy="fleetqox_semantic_contract_budgeted_deadline_first",
                control_lease_adaptive_redundancy=True,
                control_lease_adaptive_max_redundancy=3,
                control_lease_adaptive_extra_quota_scale=1.0,
            )
        )
        events = [
            {
                "event_id": index,
                "event_type": "packet",
                "flow_class": "control",
                "robot_id": f"robot_{index:04d}",
                "action": "send_intent",
                "wire_mode": "control_intent",
                "bytes": 48,
                "deadline_ms": 293.75,
                "link_loss": 0.03,
                "link_rtt_ms": 160.0,
                "link_jitter_ms": 25.0,
                "tick": 10,
                "reason": "base",
            }
            for index in range(8)
        ]
        try:
            annotated = runtime._annotate_control_lease_redundancy_to_events(events)
        finally:
            runtime.close()

        adaptive = [
            event
            for event in annotated
            if int(event["control_lease_redundancy"]) == 3
        ]
        deferred = [
            event
            for event in annotated
            if event.get("control_lease_adaptive_quota_deferred")
        ]

        self.assertEqual(len(adaptive), 3)
        self.assertEqual(len(deferred), 5)
        self.assertTrue(all(int(event["control_lease_redundancy"]) == 2 for event in deferred))

    def test_transition_guard_control_lease_extra_copies_bypass_quota(self) -> None:
        runtime = SidecarRuntime(
            RuntimeConfig(
                policy="fleetqox_semantic_contract_budgeted_deadline_first",
                control_lease_adaptive_redundancy=True,
                control_lease_adaptive_max_redundancy=3,
                control_lease_adaptive_extra_quota_scale=1.0,
            )
        )
        events = [
            {
                "event_id": index,
                "event_type": "packet",
                "flow_class": "control",
                "robot_id": f"robot_{index:04d}",
                "action": "send_intent",
                "wire_mode": "control_intent",
                "bytes": 48,
                "deadline_ms": 90.0,
                "link_loss": 0.01,
                "link_rtt_ms": 40.0,
                "link_jitter_ms": 5.0,
                "tick": 10,
                "reason": "base",
                "transport_binding_estimate": {
                    "profile": "wifi",
                    "candidate_profile": "wifi",
                    "confidence": 0.42,
                    "margin": 0.05,
                    "changed": False,
                    "dwell_ticks": 10,
                },
            }
            for index in range(8)
        ]
        try:
            annotated = runtime._annotate_control_lease_redundancy_to_events(events)
        finally:
            runtime.close()

        self.assertTrue(
            all(int(event["control_lease_redundancy"]) == 3 for event in annotated)
        )
        self.assertTrue(all(event.get("control_lease_transition_guard") for event in annotated))
        self.assertFalse(any(event.get("control_lease_adaptive_quota_deferred") for event in annotated))

    def test_paced_control_lease_retransmit_flush_is_attempt_fair(self) -> None:
        class FakeUdp:
            def __init__(self) -> None:
                self.payloads: list[bytes] = []

            def sendto(self, payload: bytes, _addr) -> None:
                self.payloads.append(payload)

            def close(self) -> None:
                pass

        runtime = SidecarRuntime(
            RuntimeConfig(
                control_lease_retransmit_max_per_tick=None,
                control_lease_terminal_replay_enabled=False,
            )
        )
        fake_udp = FakeUdp()
        runtime._udp.close()
        runtime._udp = fake_udp
        runtime._pending_control_lease_retransmits = [
            {
                "event_type": "packet",
                "flow_class": "control",
                "robot_id": robot_id,
                "event_id": event_id,
                "action": "send_intent",
                "wire_mode": "control_intent",
                "bytes": 48,
                "paced_retransmit_attempt": attempt,
            }
            for robot_id, event_id in (("robot_0000", 0), ("robot_0001", 1))
            for attempt in (1, 2)
        ]
        try:
            flushed = runtime._flush_paced_control_lease_retransmits("event_json")
            remaining = list(runtime._pending_control_lease_retransmits)
            runtime._pending_control_lease_retransmits = []
        finally:
            runtime.close()

        self.assertEqual(flushed, 2)
        self.assertEqual(
            [(event["robot_id"], event["paced_retransmit_attempt"]) for event in remaining],
            [("robot_0000", 2), ("robot_0001", 2)],
        )
        sent = [
            json.loads(payload.rstrip(b" ").decode("utf-8"))
            for payload in fake_udp.payloads
        ]
        self.assertEqual(
            [(event["robot_id"], event["paced_retransmit_attempt"]) for event in sent],
            [("robot_0000", 1), ("robot_0001", 1)],
        )

    def test_stop_drains_pending_paced_control_lease_retransmits(self) -> None:
        class FakeUdp:
            def __init__(self) -> None:
                self.payloads: list[bytes] = []

            def sendto(self, payload: bytes, _addr) -> None:
                self.payloads.append(payload)

            def close(self) -> None:
                pass

        runtime = SidecarRuntime(
            RuntimeConfig(
                policy="fleetqox_semantic_contract_budgeted_deadline_first",
                control_lease_redundancy=2,
                control_lease_paced_redundancy=True,
                control_lease_terminal_replay_interval_s=0.0,
            )
        )
        fake_udp = FakeUdp()
        runtime._udp.close()
        runtime._udp = fake_udp
        event = {
            "event_type": "packet",
            "flow_class": "control",
            "robot_id": "robot_0000",
            "action": "send_intent",
            "wire_mode": "control_intent",
            "bytes": 48,
            "deadline_ms": 90.0,
            "reason": "base",
        }
        try:
            annotated = runtime._annotate_control_lease_redundancy(event)
            emitted = runtime._emit_event_with_redundancy(annotated, "event_json")
            self.assertEqual(emitted, 1)
            self.assertEqual(len(runtime._pending_control_lease_retransmits), 1)

            stop = runtime.process_message({"type": "stop"})
        finally:
            runtime.close()

        self.assertEqual(stop["status"], "stopping")
        self.assertEqual(stop["emitted"], 3)
        self.assertEqual(stop["drain_grace_s"], 1.0)
        self.assertEqual(len(fake_udp.payloads), 4)
        retransmit = json.loads(fake_udp.payloads[1].rstrip(b" ").decode("utf-8"))
        self.assertEqual(retransmit["paced_retransmit_attempt"], 1)
        self.assertNotIn("_packet_format", retransmit)
        replay_attempts = [
            json.loads(payload.rstrip(b" ").decode("utf-8")).get(
                "terminal_replay_attempt"
            )
            for payload in fake_udp.payloads[2:]
        ]
        self.assertEqual(replay_attempts, [1, 2])

    def test_control_lease_ack_feedback_clears_tracked_retransmit(self) -> None:
        class FakeUdp:
            def __init__(self) -> None:
                self.payloads: list[bytes] = []

            def sendto(self, payload: bytes, _addr) -> None:
                self.payloads.append(payload)

            def close(self) -> None:
                pass

        runtime = SidecarRuntime(
            RuntimeConfig(
                control_lease_redundancy=1,
                control_lease_paced_redundancy=False,
                control_lease_ack_retransmit_enabled=True,
            )
        )
        fake_udp = FakeUdp()
        runtime._udp.close()
        runtime._udp = fake_udp
        event = {
            "event_id": 41,
            "event_type": "packet",
            "flow_class": "control",
            "robot_id": "robot_0000",
            "action": "send_intent",
            "wire_mode": "control_intent",
            "bytes": 48,
        }
        try:
            runtime._emit_event_with_redundancy(event, "event_json")
            response = runtime.process_message(
                {
                    "type": "robot_feedback",
                    "feedback": [
                        {
                            "source": "egress",
                            "robot_id": "robot_0000",
                            "control_lease_event_ids": [41],
                        }
                    ],
                }
            )
            flushed = runtime._flush_control_lease_ack_retransmits(
                "event_json",
                tick=1,
            )
        finally:
            runtime.close()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["feedback_type"], "control_lease_ack")
        self.assertEqual(response["applied"], 1)
        self.assertEqual(flushed, 0)
        self.assertEqual(runtime._control_lease_ack_tracker, {})

    def test_control_lease_ack_feedback_can_clear_by_source_sequence(self) -> None:
        class FakeUdp:
            def __init__(self) -> None:
                self.payloads: list[bytes] = []

            def sendto(self, payload: bytes, _addr) -> None:
                self.payloads.append(payload)

            def close(self) -> None:
                pass

        runtime = SidecarRuntime(
            RuntimeConfig(
                control_lease_redundancy=1,
                control_lease_paced_redundancy=False,
                control_lease_ack_retransmit_enabled=True,
                control_lease_ack_retransmit_timeout_ms=0.0,
            )
        )
        fake_udp = FakeUdp()
        runtime._udp.close()
        runtime._udp = fake_udp
        event = {
            "event_id": 43,
            "event_type": "packet",
            "flow_class": "control",
            "robot_id": "robot_0000",
            "topic": "/robot_0000/cmd_vel",
            "action": "send_intent",
            "wire_mode": "control_intent",
            "bytes": 48,
            "source_sample_id": "fsid1-control-43",
            "source_metadata": {
                "sequence_number": 43,
                "source_timestamp_ns": 123_000,
            },
        }
        try:
            runtime._emit_event_with_redundancy(event, "event_json")
            response = runtime.process_message(
                {
                    "type": "robot_feedback",
                    "feedback": [
                        {
                            "source": "egress_ack",
                            "robot_id": "robot_0000",
                            "source_topic": "/robot_0000/cmd_vel",
                            "source_sequence_number": 43,
                        }
                    ],
                }
            )
            flushed = runtime._flush_control_lease_ack_retransmits(
                "event_json",
                tick=1,
            )
        finally:
            runtime.close()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["feedback_type"], "control_lease_ack")
        self.assertEqual(response["applied"], 1)
        self.assertEqual(
            response["control_lease_ack"]["source_acked_control_lease_events"],
            1,
        )
        self.assertEqual(flushed, 0)
        self.assertEqual(runtime._control_lease_ack_tracker, {})
        self.assertEqual(runtime._control_lease_ack_source_index, {})

    def test_control_lease_ack_nack_gap_requests_source_sequence_retransmit(self) -> None:
        class FakeUdp:
            def __init__(self) -> None:
                self.payloads: list[bytes] = []

            def sendto(self, payload: bytes, _addr) -> None:
                self.payloads.append(payload)

            def close(self) -> None:
                pass

        runtime = SidecarRuntime(
            RuntimeConfig(
                control_lease_redundancy=1,
                control_lease_paced_redundancy=False,
                control_lease_ack_retransmit_enabled=True,
                control_lease_ack_retransmit_max_attempts=1,
                control_lease_ack_retransmit_timeout_ms=10_000.0,
            )
        )
        fake_udp = FakeUdp()
        runtime._udp.close()
        runtime._udp = fake_udp
        event = {
            "event_id": 44,
            "event_type": "packet",
            "flow_class": "control",
            "robot_id": "robot_0000",
            "topic": "/robot_0000/cmd_vel",
            "action": "send_intent",
            "wire_mode": "control_intent",
            "bytes": 48,
            "deadline_ms": 90.0,
            "reason": "base",
            "source_sample_id": "fsid1-control-44",
            "source_metadata": {
                "sequence_number": 2,
                "source_timestamp_ns": 2_000_000,
            },
        }
        try:
            runtime._emit_event_with_redundancy(event, "event_json")
            response = runtime.process_message(
                {
                    "type": "robot_feedback",
                    "feedback": [
                        {
                            "schema_version": "fleetrmw.ack_nack.v1",
                            "kind": "source_sequence_ack_nack",
                            "robot_id": "robot_0000",
                            "source_topic": "/robot_0000/cmd_vel",
                            "stream_key": [
                                "source_stream",
                                "robot_0000",
                                "/robot_0000/cmd_vel",
                            ],
                            "nack": {
                                "missing_sequence_ranges": [[2, 2]],
                            },
                        }
                    ],
                }
            )
            flushed = runtime._flush_control_lease_ack_retransmits(
                "event_json",
                tick=2,
            )
        finally:
            runtime.close()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["feedback_type"], "control_lease_ack")
        self.assertEqual(response["applied"], 0)
        self.assertEqual(response["control_lease_ack"]["nack_feedback_records"], 1)
        self.assertEqual(
            response["control_lease_ack"]["nack_requested_control_lease_events"],
            1,
        )
        self.assertEqual(flushed, 1)
        self.assertEqual(len(fake_udp.payloads), 2)
        retransmit = json.loads(fake_udp.payloads[1].rstrip(b" ").decode("utf-8"))
        self.assertEqual(retransmit["event_id"], 44)
        self.assertEqual(retransmit["ack_retransmit_attempt"], 1)
        self.assertIn("control_lease_ack_retransmit=1", retransmit["reason"])

    def test_ack_history_keeps_horizon_for_late_sequence_nack(self) -> None:
        class FakeUdp:
            def __init__(self) -> None:
                self.payloads: list[bytes] = []

            def sendto(self, payload: bytes, _addr) -> None:
                self.payloads.append(payload)

            def close(self) -> None:
                pass

        runtime = SidecarRuntime(
            RuntimeConfig(
                control_lease_redundancy=1,
                control_lease_paced_redundancy=False,
                control_lease_ack_retransmit_enabled=True,
                control_lease_ack_history_per_robot=4,
                control_lease_ack_retransmit_max_attempts=1,
                control_lease_ack_retransmit_timeout_ms=10_000.0,
            )
        )
        fake_udp = FakeUdp()
        runtime._udp.close()
        runtime._udp = fake_udp
        try:
            for sequence in range(1, 11):
                runtime._emit_event_with_redundancy(
                    {
                        "event_id": sequence,
                        "event_type": "packet",
                        "flow_class": "control",
                        "robot_id": "robot_0000",
                        "topic": "/robot_0000/cmd_vel",
                        "action": "send_intent",
                        "wire_mode": "control_intent",
                        "bytes": 48,
                        "deadline_ms": 90.0,
                        "source_deadline_ms": 45.0,
                        "source_metadata": {
                            "sequence_number": sequence,
                            "source_timestamp_ns": sequence * 1000,
                        },
                    },
                    "event_json",
                )
            response = runtime.process_message(
                {
                    "type": "robot_feedback",
                    "feedback": [
                        {
                            "schema_version": "fleetrmw.ack_nack.v1",
                            "kind": "source_sequence_ack_nack",
                            "robot_id": "robot_0000",
                            "source_topic": "/robot_0000/cmd_vel",
                            "stream_key": [
                                "source_stream",
                                "robot_0000",
                                "/robot_0000/cmd_vel",
                            ],
                            "nack": {
                                "missing_sequence_ranges": [[1, 1]],
                            },
                        }
                    ],
                }
            )
            flushed = runtime._flush_control_lease_ack_retransmits(
                "event_json",
                tick=11,
            )
        finally:
            runtime.close()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(
            response["control_lease_ack"]["nack_requested_control_lease_events"],
            1,
        )
        self.assertGreater(len(runtime._control_lease_ack_tracker), 4)
        self.assertGreaterEqual(
            runtime._control_lease_ack_history_limit("robot_0000"),
            46,
        )
        self.assertEqual(flushed, 1)
        retransmit = json.loads(fake_udp.payloads[-1].rstrip(b" ").decode("utf-8"))
        self.assertEqual(retransmit["event_id"], 1)
        self.assertEqual(retransmit["ack_retransmit_attempt"], 1)

    def test_control_lease_ack_retransmits_unacked_event_after_ack_window(self) -> None:
        class FakeUdp:
            def __init__(self) -> None:
                self.payloads: list[bytes] = []

            def sendto(self, payload: bytes, _addr) -> None:
                self.payloads.append(payload)

            def close(self) -> None:
                pass

        runtime = SidecarRuntime(
            RuntimeConfig(
                control_lease_redundancy=1,
                control_lease_paced_redundancy=False,
                control_lease_ack_retransmit_enabled=True,
                control_lease_ack_retransmit_max_attempts=1,
                control_lease_ack_retransmit_timeout_ms=0.0,
            )
        )
        fake_udp = FakeUdp()
        runtime._udp.close()
        runtime._udp = fake_udp
        event = {
            "event_id": 42,
            "event_type": "packet",
            "flow_class": "control",
            "robot_id": "robot_0000",
            "action": "send_intent",
            "wire_mode": "control_intent",
            "bytes": 48,
            "deadline_ms": 90.0,
            "reason": "base",
        }
        try:
            runtime._emit_event_with_redundancy(event, "event_json")
            runtime.process_message(
                {
                    "type": "robot_feedback",
                    "feedback": [
                        {
                            "source": "egress",
                            "robot_id": "robot_0000",
                            "control_lease_event_ids": [999],
                        }
                    ],
                }
            )
            flushed = runtime._flush_control_lease_ack_retransmits(
                "event_json",
                tick=1,
            )
        finally:
            runtime.close()

        self.assertEqual(flushed, 1)
        self.assertEqual(len(fake_udp.payloads), 2)
        retransmit = json.loads(fake_udp.payloads[1].rstrip(b" ").decode("utf-8"))
        self.assertEqual(retransmit["event_id"], 42)
        self.assertEqual(retransmit["ack_retransmit_attempt"], 1)
        self.assertIn("control_lease_ack_retransmit=1", retransmit["reason"])

    def test_terminal_replay_keeps_recent_control_lease_history_per_robot(self) -> None:
        class FakeUdp:
            def __init__(self) -> None:
                self.payloads: list[bytes] = []

            def sendto(self, payload: bytes, _addr) -> None:
                self.payloads.append(payload)

            def close(self) -> None:
                pass

        runtime = SidecarRuntime(
            RuntimeConfig(
                control_lease_redundancy=1,
                control_lease_paced_redundancy=False,
                control_lease_terminal_replay_interval_s=0.0,
                control_lease_terminal_replay_history_per_robot=3,
            )
        )
        fake_udp = FakeUdp()
        runtime._udp.close()
        runtime._udp = fake_udp
        try:
            for event_id in range(4):
                runtime._emit_event_with_redundancy(
                    {
                        "event_id": event_id,
                        "event_type": "packet",
                        "flow_class": "control",
                        "robot_id": "robot_0000",
                        "action": "send_intent",
                        "wire_mode": "control_intent",
                        "bytes": 48,
                    },
                    "event_json",
                )
            stop = runtime.process_message({"type": "stop"})
        finally:
            runtime.close()

        self.assertEqual(stop["emitted"], 6)
        replayed = [
            json.loads(payload.rstrip(b" ").decode("utf-8"))["event_id"]
            for payload in fake_udp.payloads[4:]
        ]
        self.assertEqual(replayed, [1, 2, 3, 1, 2, 3])

    def test_high_loss_control_lease_requests_same_batch_drain(self) -> None:
        runtime = SidecarRuntime(
            RuntimeConfig(policy="fleetqox_semantic_contract_budgeted_deadline_first")
        )
        try:
            roaming_event = runtime._annotate_control_lease_redundancy(
                {
                    "event_type": "packet",
                    "flow_class": "control",
                    "action": "send_intent",
                    "wire_mode": "control_intent",
                    "deadline_ms": 293.75,
                    "link_loss": 0.03,
                    "link_rtt_ms": 160.0,
                    "link_jitter_ms": 25.0,
                }
            )
            wan_event = runtime._annotate_control_lease_redundancy(
                {
                    "event_type": "packet",
                    "flow_class": "control",
                    "action": "send_intent",
                    "wire_mode": "control_intent",
                    "deadline_ms": 90.0,
                    "link_loss": 0.015,
                    "link_rtt_ms": 120.0,
                    "link_jitter_ms": 15.0,
                }
            )
        finally:
            runtime.close()

        self.assertTrue(runtime._control_lease_same_batch_drain_required([roaming_event]))
        self.assertFalse(runtime._control_lease_same_batch_drain_required([wan_event]))

    def test_transport_volatility_guard_defers_noncontrol_packets(self) -> None:
        event = {
            "event_type": "packet",
            "flow_class": "perception",
            "action": "send",
            "wire_mode": "native",
            "bytes": 512,
            "degraded": False,
            "reason": "base",
        }
        estimate = {
            "profile": "wifi",
            "candidate_profile": "wifi",
            "confidence": 0.42,
            "margin": 0.05,
            "changed": True,
            "dwell_ticks": 0,
        }

        guarded = apply_transport_volatility_guard(event, estimate)

        self.assertTrue(transport_volatility_guard_applies(event, estimate))
        self.assertEqual(guarded["event_type"], "decision")
        self.assertEqual(guarded["action"], "defer")
        self.assertEqual(guarded["bytes"], 0)
        self.assertEqual(guarded["wire_mode"], "")
        self.assertIn("transport_volatility_guard", guarded["reason"])

    def test_transport_volatility_guard_preserves_control_lease(self) -> None:
        event = {
            "event_type": "packet",
            "flow_class": "control",
            "action": "send_intent",
            "wire_mode": "control_intent",
            "bytes": 48,
            "degraded": False,
            "reason": "base",
        }
        estimate = {"confidence": 0.1, "margin": 0.01, "changed": True, "dwell_ticks": 0}

        guarded = apply_transport_volatility_guard(event, estimate)

        self.assertEqual(guarded["event_type"], "packet")
        self.assertEqual(guarded["action"], "send_intent")
        self.assertEqual(guarded["wire_mode"], "control_intent")

    def test_transport_volatility_guard_preserves_stable_noncontrol_packet(self) -> None:
        event = {
            "event_type": "packet",
            "flow_class": "state",
            "action": "send",
            "wire_mode": "native",
            "bytes": 256,
            "degraded": False,
            "reason": "base",
        }
        estimate = {
            "confidence": 0.9,
            "margin": 0.2,
            "changed": False,
            "dwell_ticks": 8,
        }

        guarded = apply_transport_volatility_guard(event, estimate)

        self.assertEqual(guarded["event_type"], "packet")
        self.assertEqual(guarded["action"], "send")

    def test_runtime_transport_volatility_guard_allows_bounded_low_cost_probe(self) -> None:
        runtime = SidecarRuntime(
            RuntimeConfig(
                udp_host="127.0.0.1",
                udp_port=_free_udp_port(),
                transport_volatility_probe_period_ticks=4,
            )
        )
        estimate = {
            "profile": "wifi",
            "candidate_profile": "wan",
            "confidence": 0.55,
            "margin": 0.20,
            "changed": False,
            "dwell_ticks": 8,
        }
        event = {
            "event_type": "packet",
            "flow_class": "perception",
            "robot_id": "robot_0000",
            "action": "send_degraded",
            "wire_mode": "degraded",
            "bytes": 96,
            "predicted_slack_ms": 12.0,
            "tick": 10,
            "degraded": True,
            "reason": "base",
        }
        try:
            first = runtime._apply_transport_volatility_guard(event, estimate)
            second = runtime._apply_transport_volatility_guard(event | {"tick": 12}, estimate)
            third = runtime._apply_transport_volatility_guard(event | {"tick": 14}, estimate)
        finally:
            runtime.close()

        self.assertEqual(first["event_type"], "packet")
        self.assertEqual(first["action"], "send_degraded")
        self.assertIn("transport_volatility_guard=allow_probe", first["reason"])
        self.assertEqual(second["event_type"], "decision")
        self.assertEqual(second["action"], "defer")
        self.assertEqual(third["event_type"], "packet")

    def test_runtime_transport_volatility_guard_applies_fleet_probe_quota(self) -> None:
        runtime = SidecarRuntime(
            RuntimeConfig(
                udp_host="127.0.0.1",
                udp_port=_free_udp_port(),
                transport_volatility_probe_max_per_tick=2,
                transport_volatility_probe_max_per_robot_per_tick=1,
                transport_volatility_probe_period_ticks=1,
            )
        )
        estimate = {
            "profile": "wan",
            "candidate_profile": "wan",
            "confidence": 0.62,
            "margin": 0.24,
            "changed": False,
            "dwell_ticks": 9,
        }
        events = []
        event_id = 0
        for robot_index in range(4):
            robot_id = f"robot_{robot_index:04d}"
            for flow_class, action, wire_mode, utility in (
                ("state", "send_compacted", "semantic_delta", 20.0),
                ("perception", "send_degraded", "degraded", 10.0),
            ):
                events.append(
                    {
                        "event_id": event_id,
                        "event_type": "packet",
                        "flow_id": f"{robot_id}:{flow_class}",
                        "flow_class": flow_class,
                        "robot_id": robot_id,
                        "action": action,
                        "wire_mode": wire_mode,
                        "bytes": 96,
                        "predicted_slack_ms": 12.0,
                        "semantic_utility": utility,
                        "tick": 10,
                        "degraded": action == "send_degraded",
                        "reason": "base",
                    }
                )
                event_id += 1
        try:
            first = runtime._apply_transport_volatility_guard_to_events(events, estimate)
            second = runtime._apply_transport_volatility_guard_to_events(
                [event | {"tick": 11} for event in events],
                estimate,
            )
        finally:
            runtime.close()

        first_packets = [event for event in first if event["event_type"] == "packet"]
        second_packets = [event for event in second if event["event_type"] == "packet"]
        first_robots = {event["robot_id"] for event in first_packets}
        second_robots = {event["robot_id"] for event in second_packets}

        self.assertEqual(len(first_packets), 2)
        self.assertEqual(len(first_robots), 2)
        self.assertEqual(len(second_packets), 2)
        self.assertEqual(len(second_robots), 2)
        self.assertTrue(first_robots.isdisjoint(second_robots))

    def test_runtime_transport_volatility_guard_recovers_uncertain_semantic_probes(self) -> None:
        runtime = SidecarRuntime(
            RuntimeConfig(
                udp_host="127.0.0.1",
                udp_port=_free_udp_port(),
                transport_volatility_probe_max_per_tick=2,
                transport_volatility_probe_max_per_robot_per_tick=1,
                transport_volatility_probe_period_ticks=1,
            )
        )
        estimate = {
            "profile": "wifi",
            "candidate_profile": "wifi",
            "confidence": 0.24,
            "margin": 0.02,
            "changed": True,
            "dwell_ticks": 0,
        }
        events = []
        event_id = 0
        for robot_index in range(4):
            robot_id = f"robot_{robot_index:04d}"
            for flow_class, topic, msg_type, utility in (
                ("state", f"/{robot_id}/odom", "nav_msgs/msg/Odometry", 20.0),
                ("perception", f"/{robot_id}/scan", "sensor_msgs/msg/LaserScan", 10.0),
            ):
                events.append(
                    {
                        "event_id": event_id,
                        "event_type": "packet",
                        "flow_id": f"{robot_id}:{flow_class}",
                        "flow_class": flow_class,
                        "robot_id": robot_id,
                        "action": "send",
                        "wire_mode": "native",
                        "bytes": 256,
                        "predicted_slack_ms": 24.0,
                        "semantic_utility": utility,
                        "tick": 10,
                        "degraded": False,
                        "topic": topic,
                        "source_msg_type": msg_type,
                        "semantic_payload": {"msg_type": msg_type},
                        "reason": "base",
                    }
                )
                event_id += 1
        try:
            guarded = runtime._apply_transport_volatility_guard_to_events(
                events,
                estimate,
            )
        finally:
            runtime.close()

        packets = [event for event in guarded if event["event_type"] == "packet"]
        deferred = [event for event in guarded if event["event_type"] == "decision"]

        self.assertEqual(len(packets), 2)
        self.assertEqual(len({event["robot_id"] for event in packets}), 2)
        self.assertEqual(len(deferred), 6)
        self.assertFalse(any(event["wire_mode"] == "native" for event in packets))
        self.assertTrue(
            all(
                event["action"] in {"send_compacted", "send_degraded"}
                for event in packets
            )
        )
        self.assertTrue(
            all(
                "transport_volatility_recovery_probe" in str(event["reason"])
                for event in packets
            )
        )
        self.assertTrue(
            all(
                "transport_volatility_guard=allow_probe" in str(event["reason"])
                for event in packets
            )
        )

    def test_runtime_transport_volatility_guard_never_probes_native_noncontrol(self) -> None:
        runtime = SidecarRuntime(
            RuntimeConfig(
                udp_host="127.0.0.1",
                udp_port=_free_udp_port(),
                transport_volatility_probe_period_ticks=1,
            )
        )
        estimate = {
            "confidence": 0.4,
            "margin": 0.05,
            "changed": False,
            "dwell_ticks": 4,
        }
        event = {
            "event_type": "packet",
            "flow_class": "state",
            "robot_id": "robot_0000",
            "action": "send",
            "wire_mode": "native",
            "bytes": 512,
            "predicted_slack_ms": 50.0,
            "tick": 1,
            "degraded": False,
            "reason": "base",
        }
        try:
            guarded = runtime._apply_transport_volatility_guard(event, estimate)
        finally:
            runtime.close()

        self.assertEqual(guarded["event_type"], "decision")
        self.assertEqual(guarded["action"], "defer")
        self.assertIn("transport_volatility_guard=defer_noncontrol", guarded["reason"])

    def test_process_batch_logs_and_emits_udp_packet(self) -> None:
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            receiver.bind(("127.0.0.1", 0))
        except PermissionError as exc:
            receiver.close()
            raise unittest.SkipTest("sandbox disallows local UDP bind") from exc
        receiver.settimeout(1.0)
        udp_port = int(receiver.getsockname()[1])
        batches = generate_synthetic_batches(
            scenario="runtime_test",
            robots=2,
            seconds=1,
            seed=7,
            capacity_bytes_per_second=80_000,
            max_ticks=1,
        )

        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "decisions.jsonl"
            runtime = SidecarRuntime(
                RuntimeConfig(
                    udp_host="127.0.0.1",
                    udp_port=udp_port,
                    decision_log=log_path,
                )
            )
            try:
                response = runtime.process_batch(batches[0])
                self.assertGreater(response["emitted"], 0)
                data, _ = receiver.recvfrom(64_000)
            finally:
                runtime.close()
                receiver.close()

            received = json.loads(data.rstrip(b" ").decode("utf-8"))
            validate_event(received)
            lines = log_path.read_text(encoding="utf-8").splitlines()

        self.assertTrue(lines)
        self.assertEqual(received["schema_version"], "fleetrmw.sidecar.trace.v1")
        self.assertIn(received["action"], {"send", "send_degraded", "send_compacted"})

    def test_process_batch_can_emit_data_frame_udp_packet(self) -> None:
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            receiver.bind(("127.0.0.1", 0))
        except PermissionError as exc:
            receiver.close()
            raise unittest.SkipTest("sandbox disallows local UDP bind") from exc
        receiver.settimeout(1.0)
        udp_port = int(receiver.getsockname()[1])
        batch = generate_synthetic_batches(
            scenario="runtime_frame_test",
            robots=1,
            seconds=1,
            seed=7,
            capacity_bytes_per_second=80_000,
            max_ticks=1,
        )[0]

        runtime = SidecarRuntime(
            RuntimeConfig(
                udp_host="127.0.0.1",
                udp_port=udp_port,
                packet_format="data_frame",
            )
        )
        try:
            response = runtime.process_batch(batch)
            self.assertGreater(response["emitted"], 0)
            data, _ = receiver.recvfrom(64_000)
        finally:
            runtime.close()
            receiver.close()

        received = decode_sidecar_packet(data)

        self.assertIsNotNone(received)
        assert received is not None
        validate_event(received)
        self.assertEqual(received["schema_version"], "fleetrmw.sidecar.trace.v1")
        self.assertRegex(str(received["data_frame_id"]), r"^ffrm1-[0-9a-f]{32}$")

    def test_process_batch_can_use_transport_binding_packet_format(self) -> None:
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            receiver.bind(("127.0.0.1", 0))
        except PermissionError as exc:
            receiver.close()
            raise unittest.SkipTest("sandbox disallows local UDP bind") from exc
        receiver.settimeout(1.0)
        udp_port = int(receiver.getsockname()[1])
        batch = generate_synthetic_batches(
            scenario="runtime_binding_test",
            robots=1,
            seconds=1,
            seed=7,
            capacity_bytes_per_second=80_000,
            max_ticks=1,
        )[0]
        batch["transport_binding"] = TransportBinding(
            profile="wifi",
            objective="balanced_safety_utility",
            policy="data_frame/rmw_zenoh_cpp",
            packet_format="data_frame",
            rmw="rmw_zenoh_cpp",
            score=1.0,
        ).as_payload()
        batch["transport_binding_estimate"] = {
            "profile": "wifi",
            "candidate_profile": "wifi",
            "confidence": 0.9,
            "margin": 0.2,
            "changed": True,
            "dwell_ticks": 0,
        }

        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "decisions.jsonl"
            runtime = SidecarRuntime(
                RuntimeConfig(
                    udp_host="127.0.0.1",
                    udp_port=udp_port,
                    decision_log=log_path,
                )
            )
            try:
                response = runtime.process_batch(batch)
                self.assertEqual(response["packet_format"], "data_frame")
                self.assertEqual(
                    response["transport_binding_estimate"]["profile"],
                    "wifi",
                )
                data, _ = receiver.recvfrom(64_000)
            finally:
                runtime.close()
                receiver.close()
            event = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        received = decode_sidecar_packet(data)

        self.assertIsNotNone(received)
        assert received is not None
        self.assertEqual(
            event["transport_binding"]["policy"],
            "data_frame/rmw_zenoh_cpp",
        )
        self.assertEqual(event["transport_binding_estimate"]["profile"], "wifi")
        self.assertRegex(str(received["data_frame_id"]), r"^ffrm1-[0-9a-f]{32}$")

    def test_process_batch_actuates_fleet_optimizer_redundant_paths(self) -> None:
        class FakeUdp:
            def __init__(self) -> None:
                self.payloads: list[bytes] = []
                self.addrs: list[tuple[str, int]] = []

            def sendto(self, payload: bytes, addr) -> None:
                self.payloads.append(payload)
                self.addrs.append(addr)

            def close(self) -> None:
                pass

        flow = _runtime_flow(
            flow_class=FlowClass.CONTROL,
            deadline_ms=30.0,
            lifespan_ms=90.0,
        )
        obs = _runtime_obs(flow)
        batch = {
            "type": "batch",
            "scenario": "runtime_fleet_optimizer_redundant",
            "timestamp_ms": 0.0,
            "tick": 1,
            "link": {
                "capacity_bytes_per_tick": 4096,
                "loss": 0.18,
                "jitter_ms": 18.0,
                "rtt_ms": 90.0,
            },
            "flows": [
                {
                    "flow": flow_spec_to_payload(flow),
                    "observation": observation_to_payload(obs),
                }
            ],
            "fleet_optimizer": {
                "enabled": True,
                "capacity_bytes_per_tick": 4096,
                "redundant_deadline_ms": 35.0,
                "redundancy_risk_threshold": 1.0,
                "path_targets": {
                    "primary_wifi": {"udp_host": "127.0.0.1", "udp_port": 19101},
                    "backup_5g": {"udp_host": "127.0.0.1", "udp_port": 19102},
                },
                "paths": [
                    {
                        "path_id": "primary_wifi",
                        "latency_ms": 60.0,
                        "jitter_ms": 20.0,
                        "loss": 0.18,
                        "nack_rate": 0.16,
                        "deadline_miss_ratio": 0.24,
                        "bandwidth_utilization": 0.88,
                    },
                    {
                        "path_id": "backup_5g",
                        "latency_ms": 24.0,
                        "jitter_ms": 5.0,
                        "loss": 0.035,
                        "nack_rate": 0.025,
                        "deadline_miss_ratio": 0.04,
                        "bandwidth_utilization": 0.42,
                    },
                ],
                "robot_states": [
                    {
                        "robot_id": "robot_0000",
                        "control_delivery_ratio": 0.90,
                        "deadline_miss_ratio": 0.18,
                        "qoe_score": 0.78,
                    }
                ],
            },
        }
        runtime = SidecarRuntime(
            RuntimeConfig(
                policy="static_priority",
                control_lease_redundancy=1,
                control_lease_paced_redundancy=False,
            )
        )
        fake_udp = FakeUdp()
        runtime._udp.close()
        runtime._udp = fake_udp
        try:
            response = runtime.process_batch(batch)
        finally:
            runtime.close()

        self.assertEqual(response["fleet_optimizer"]["schema_version"], "fleetrmw.fleet_optimizer_runtime.v1")
        self.assertEqual(response["fleet_optimizer"]["redundant_count"], 1)
        self.assertEqual(response["emitted"], 2)
        self.assertEqual(len(fake_udp.payloads), 2)
        self.assertEqual(
            fake_udp.addrs,
            [("127.0.0.1", 19102), ("127.0.0.1", 19101)],
        )
        event = json.loads(fake_udp.payloads[0].rstrip(b" ").decode("utf-8"))
        validate_event(event)
        self.assertEqual(event["fleet_transport_mode"], "redundant")
        self.assertEqual(event["fleet_transport_paths"], ["backup_5g", "primary_wifi"])
        self.assertEqual(event["fleet_transport_path"], "backup_5g")
        self.assertEqual(event["fleet_udp_target"]["udp_port"], 19102)
        self.assertEqual(event["fleet_path_redundancy"], 2)
        self.assertEqual(event["fleet_optimizer"]["mode"], "redundant")

    def test_process_batch_degrades_with_fleet_optimizer_capacity_pressure(self) -> None:
        class FakeUdp:
            def __init__(self) -> None:
                self.payloads: list[bytes] = []

            def sendto(self, payload: bytes, _addr) -> None:
                self.payloads.append(payload)

            def close(self) -> None:
                pass

        flow = _runtime_flow(
            flow_class=FlowClass.PERCEPTION,
            deadline_ms=120.0,
            lifespan_ms=250.0,
        )
        obs = _runtime_obs(flow)
        batch = {
            "type": "batch",
            "scenario": "runtime_fleet_optimizer_degraded",
            "timestamp_ms": 0.0,
            "tick": 1,
            "link": {
                "capacity_bytes_per_tick": 4096,
                "loss": 0.02,
                "jitter_ms": 4.0,
                "rtt_ms": 25.0,
            },
            "flows": [
                {
                    "flow": flow_spec_to_payload(flow),
                    "observation": observation_to_payload(obs),
                }
            ],
            "fleet_optimizer": {
                "enabled": True,
                "capacity_bytes_per_tick": 100,
                "degrade_floor": 0.35,
                "paths": [
                    {
                        "path_id": "backup_5g",
                        "latency_ms": 24.0,
                        "jitter_ms": 5.0,
                        "loss": 0.035,
                    }
                ],
            },
        }
        runtime = SidecarRuntime(RuntimeConfig(policy="static_priority"))
        fake_udp = FakeUdp()
        runtime._udp.close()
        runtime._udp = fake_udp
        try:
            response = runtime.process_batch(batch)
        finally:
            runtime.close()

        self.assertEqual(response["fleet_optimizer"]["degraded_count"], 1)
        self.assertEqual(response["emitted"], 1)
        event = json.loads(fake_udp.payloads[0].rstrip(b" ").decode("utf-8"))
        validate_event(event)
        self.assertEqual(event["action"], "send_degraded")
        self.assertEqual(event["wire_mode"], "degraded")
        self.assertEqual(event["fleet_transport_mode"], "degraded")
        self.assertEqual(event["bytes"], 84)

    def test_tcp_runtime_accepts_synthetic_batches(self) -> None:
        listen_port = _free_port()
        udp_port = _free_port()
        with TemporaryDirectory() as tmpdir:
            runtime = SidecarRuntime(
                RuntimeConfig(
                    udp_host="127.0.0.1",
                    udp_port=udp_port,
                    decision_log=Path(tmpdir) / "decisions.jsonl",
                )
            )
            thread = threading.Thread(
                target=serve_tcp,
                kwargs={
                    "host": "127.0.0.1",
                    "port": listen_port,
                    "runtime": runtime,
                    "idle_timeout_s": 5.0,
                    "max_runtime_s": 5.0,
                },
                daemon=True,
            )
            thread.start()
            batches = generate_synthetic_batches(
                scenario="runtime_tcp_test",
                robots=1,
                seconds=1,
                seed=11,
                capacity_bytes_per_second=80_000,
                max_ticks=1,
            )
            responses = send_batches(host="127.0.0.1", port=listen_port, batches=batches)
            thread.join(timeout=2.0)
            runtime.close()

        self.assertEqual(responses[-1]["status"], "stopping")
        self.assertEqual(responses[0]["status"], "ok")

    def test_tcp_runtime_accepts_robot_feedback_while_batch_client_is_open(self) -> None:
        listen_port = _free_port()
        udp_port = _free_udp_port()
        runtime = SidecarRuntime(
            RuntimeConfig(
                udp_host="127.0.0.1",
                udp_port=udp_port,
                policy="fleetqox_semantic_contract_budgeted",
            )
        )
        thread = threading.Thread(
            target=serve_tcp,
            kwargs={
                "host": "127.0.0.1",
                "port": listen_port,
                "runtime": runtime,
                "idle_timeout_s": 5.0,
                "max_runtime_s": 5.0,
            },
            daemon=True,
        )
        thread.start()
        batch = generate_synthetic_batches(
            scenario="runtime_tcp_feedback_test",
            robots=1,
            seconds=1,
            seed=7,
            capacity_bytes_per_second=80_000,
            max_ticks=1,
        )[0]
        robot_id = str(batch["flows"][0]["flow"]["robot_id"])

        batch_conn = socket.create_connection(("127.0.0.1", listen_port), timeout=10.0)
        try:
            batch_file = batch_conn.makefile("rwb")
            batch_file.write((json.dumps(batch, sort_keys=True) + "\n").encode("utf-8"))
            batch_file.flush()
            batch_response = json.loads(batch_file.readline().decode("utf-8"))

            with socket.create_connection(("127.0.0.1", listen_port), timeout=10.0) as feedback_conn:
                feedback_file = feedback_conn.makefile("rwb")
                feedback_file.write(
                    (
                        json.dumps(
                            {
                                "type": "robot_feedback",
                                "feedback": [
                                    {
                                        "robot_id": robot_id,
                                        "control_delivery_ratio": 0.40,
                                        "deadline_miss_ratio": 0.70,
                                    }
                                ],
                            },
                            sort_keys=True,
                        )
                        + "\n"
                    ).encode("utf-8")
                )
                feedback_file.flush()
                feedback_response = json.loads(feedback_file.readline().decode("utf-8"))

            batch_file.write(b'{"type":"stop"}\n')
            batch_file.flush()
            stop_response = json.loads(batch_file.readline().decode("utf-8"))
        finally:
            batch_conn.close()
            thread.join(timeout=2.0)
            runtime.close()

        self.assertEqual(batch_response["status"], "ok")
        self.assertEqual(feedback_response["status"], "ok")
        self.assertEqual(feedback_response["applied"], 1)
        self.assertGreater(feedback_response["snapshot"][robot_id]["pressure"], 0.0)
        self.assertEqual(stop_response["status"], "stopping")

    def test_process_batch_can_return_feedback(self) -> None:
        udp_port = _free_udp_port()
        batches = generate_synthetic_batches(
            scenario="runtime_feedback_test",
            robots=1,
            seconds=1,
            seed=7,
            capacity_bytes_per_second=80_000,
            max_ticks=1,
        )
        batch = dict(batches[0])
        batch["include_feedback"] = True
        runtime = SidecarRuntime(RuntimeConfig(udp_host="127.0.0.1", udp_port=udp_port))
        try:
            response = runtime.process_batch(batch)
        finally:
            runtime.close()

        self.assertEqual(response["status"], "ok")
        self.assertIn("feedback", response)
        self.assertTrue(response["feedback"])
        self.assertIn("action_counts", response)

    def test_robot_feedback_message_updates_budget_policy_pressure(self) -> None:
        udp_port = _free_udp_port()
        batch = generate_synthetic_batches(
            scenario="runtime_robot_feedback_test",
            robots=1,
            seconds=1,
            seed=7,
            capacity_bytes_per_second=80_000,
            max_ticks=1,
        )[0]
        robot_id = str(batch["flows"][0]["flow"]["robot_id"])

        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "decisions.jsonl"
            runtime = SidecarRuntime(
                RuntimeConfig(
                    udp_host="127.0.0.1",
                    udp_port=udp_port,
                    policy="fleetqox_semantic_contract_budgeted",
                    decision_log=log_path,
                )
            )
            try:
                feedback_response = runtime.process_message(
                    {
                        "type": "robot_feedback",
                        "feedback": [
                            {
                                "robot_id": robot_id,
                                "control_delivery_ratio": 0.25,
                                "deadline_miss_ratio": 0.80,
                            }
                        ],
                    }
                )
                runtime.process_batch(batch)
            finally:
                runtime.close()
            events = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(feedback_response["status"], "ok")
        self.assertEqual(feedback_response["applied"], 1)
        self.assertGreater(
            feedback_response["snapshot"][robot_id]["pressure"],
            0.0,
        )
        self.assertTrue(
            any("robot_budget=active" in str(event.get("reason", "")) for event in events)
        )

    def test_process_batch_preserves_semantic_payload_in_events(self) -> None:
        udp_port = _free_udp_port()
        batch = generate_synthetic_batches(
            scenario="runtime_payload_test",
            robots=1,
            seconds=1,
            seed=7,
            capacity_bytes_per_second=80_000,
            max_ticks=1,
        )[0]
        batch["flows"][0]["semantic_payload"] = {
            "schema_version": "fleetrmw.semantic_payload.v1",
            "msg_type": "geometry_msgs/msg/Twist",
            "twist": {
                "linear": {"x": 0.2, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.1},
            },
        }

        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "decisions.jsonl"
            runtime = SidecarRuntime(
                RuntimeConfig(
                    udp_host="127.0.0.1",
                    udp_port=udp_port,
                    decision_log=log_path,
                )
            )
            try:
                runtime.process_batch(batch)
            finally:
                runtime.close()
            event = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(event["semantic_payload"]["msg_type"], "geometry_msgs/msg/Twist")
        self.assertEqual(event["semantic_payload"]["twist"]["angular"]["z"], 0.1)

    def test_synthetic_stream_applies_action_feedback_to_ages(self) -> None:
        stream = SyntheticBatchStream(
            scenario="closed_loop_test",
            robots=1,
            seconds=1,
            seed=7,
            capacity_bytes_per_second=80_000,
            max_ticks=1,
            include_feedback=True,
        )
        flow_id = stream.flows[0].flow_id
        stream.ages[flow_id] = 120.0

        stream.apply_feedback({"feedback": [{"flow_id": flow_id, "action": "send"}]})

        self.assertEqual(stream.ages[flow_id], 0.0)

    def test_synthetic_stream_accepts_link_profile_overrides(self) -> None:
        stream = SyntheticBatchStream(
            scenario="profile_test",
            robots=1,
            seconds=1,
            seed=7,
            capacity_bytes_per_second=90_000,
            link_rtt_ms=120.0,
            link_jitter_ms=15.0,
            link_loss=0.015,
            max_ticks=1,
        )

        link = stream.link_for_tick(10)

        self.assertEqual(link.rtt_ms, 120.0)
        self.assertEqual(link.jitter_ms, 15.0)
        self.assertAlmostEqual(link.loss, 0.015)

    def test_runtime_supports_all_policies(self) -> None:
        batches = generate_synthetic_batches(
            scenario="runtime_policy_test",
            robots=1,
            seconds=1,
            seed=7,
            capacity_bytes_per_second=80_000,
            max_ticks=1,
        )
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            receiver.bind(("127.0.0.1", 0))
        except PermissionError as exc:
            receiver.close()
            raise unittest.SkipTest("sandbox disallows local UDP bind") from exc
        udp_port = int(receiver.getsockname()[1])
        receiver.close()

        for policy in SIDECAR_POLICIES:
            runtime = SidecarRuntime(
                RuntimeConfig(
                    udp_host="127.0.0.1",
                    udp_port=udp_port,
                    policy=policy,
                    validate_events=True,
                )
            )
            try:
                response = runtime.process_batch(batches[0])
            finally:
                runtime.close()
            self.assertEqual(response["status"], "ok")

    def test_runtime_can_label_lagrangian_variant(self) -> None:
        udp_port = _free_udp_port()
        batches = generate_synthetic_batches(
            scenario="runtime_label_test",
            robots=1,
            seconds=1,
            seed=7,
            capacity_bytes_per_second=80_000,
            max_ticks=1,
        )
        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "decisions.jsonl"
            runtime = SidecarRuntime(
                RuntimeConfig(
                    udp_host="127.0.0.1",
                    udp_port=udp_port,
                    policy="fleetqox_predictive_lagrangian",
                    policy_label="lag_015",
                    lagrangian_overrides={"deadline_drop_risk": 0.45},
                    decision_log=log_path,
                )
            )
            try:
                runtime.process_batch(batches[0])
            finally:
                runtime.close()
            first = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(first["policy"], "lag_015")

    def test_lagrangian_config_from_overrides(self) -> None:
        config = lagrangian_config_from_overrides(
            {
                "deadline_risk_budget": 0.04,
                "deadline_drop_risk": 0.55,
            }
        )

        self.assertEqual(config.deadline_risk_budget, 0.04)
        self.assertEqual(config.deadline_drop_risk, 0.55)


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        try:
            sock.bind(("127.0.0.1", 0))
        except PermissionError as exc:
            raise unittest.SkipTest("sandbox disallows local TCP bind") from exc
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _runtime_flow(
    *,
    flow_class: FlowClass,
    deadline_ms: float,
    lifespan_ms: float,
) -> FlowSpec:
    return FlowSpec(
        flow_id="robot_0000:cmd",
        robot_id="robot_0000",
        topic="/robot_0000/cmd_vel",
        flow_class=flow_class,
        qos=QoSProfile(deadline_ms=deadline_ms, lifespan_ms=lifespan_ms),
        qoe=QoEProfile(operator_visible=False),
        nominal_size_bytes=240,
        nominal_rate_hz=20.0,
        causal_task_gain=1.0,
        tags={"ros2_msg_type": "geometry_msgs/msg/Twist"},
    )


def _runtime_obs(flow: FlowSpec) -> FlowObservation:
    return FlowObservation(
        age_ms=0.0,
        queue_depth=1,
        measured_loss=0.0,
        measured_rtt_ms=20.0,
        observed_jitter_ms=1.0,
        task=TaskContext(
            task_id="task",
            robot_id=flow.robot_id,
            task_criticality=0.9,
            collision_risk=0.1,
            operator_attention=0.2,
            coordination_pressure=0.3,
        ),
    )


def _free_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        try:
            sock.bind(("127.0.0.1", 0))
        except PermissionError as exc:
            raise unittest.SkipTest("sandbox disallows local UDP bind") from exc
        return int(sock.getsockname()[1])
    finally:
        sock.close()


if __name__ == "__main__":
    unittest.main()
