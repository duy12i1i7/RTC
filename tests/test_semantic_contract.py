import unittest

from fleetqox.model import (
    FlowClass,
    FlowObservation,
    FlowSpec,
    NetworkLink,
    QoEProfile,
    QoSProfile,
    TaskContext,
)
from fleetqox.semantic_contract import (
    TransformKind,
    build_flow_contract,
    transform_candidates,
)


class SemanticContractTest(unittest.TestCase):
    def test_control_contract_includes_intent_transform(self) -> None:
        control = _flow("robot_1:cmd", FlowClass.CONTROL, deadline=45)
        contract = build_flow_contract(
            control,
            _obs(control, age_ms=20),
            NetworkLink(capacity_bytes_per_tick=900, rtt_ms=120, jitter_ms=15, loss=0.015),
        )

        self.assertIsNotNone(contract.transform(TransformKind.RAW))
        self.assertIsNotNone(contract.transform(TransformKind.SEMANTIC_DELTA))
        self.assertIsNotNone(contract.transform(TransformKind.CONTROL_INTENT))
        self.assertIsNotNone(contract.transform(TransformKind.SUPERVISORY_INTENT))
        self.assertGreater(
            contract.transform(TransformKind.CONTROL_INTENT).effective_deadline_ms,
            control.qos.deadline_ms,
        )

    def test_control_intent_is_better_than_raw_when_deadline_is_infeasible(self) -> None:
        control = _flow("robot_1:cmd", FlowClass.CONTROL, deadline=45)
        candidates = transform_candidates(
            control,
            _obs(control, age_ms=20),
            NetworkLink(capacity_bytes_per_tick=756, rtt_ms=120, jitter_ms=15, loss=0.015),
        )
        by_kind = {item.transform.kind: item for item in candidates}

        self.assertFalse(by_kind[TransformKind.RAW].certificate.feasible)
        self.assertGreater(
            by_kind[TransformKind.CONTROL_INTENT].certificate.slack_after_wire_ms,
            by_kind[TransformKind.RAW].certificate.slack_after_wire_ms,
        )
        self.assertLess(
            by_kind[TransformKind.CONTROL_INTENT].allocated_bytes,
            by_kind[TransformKind.RAW].allocated_bytes,
        )

    def test_supervisory_intent_is_feasible_when_short_control_lifespan_is_not(self) -> None:
        control = _flow("robot_1:cmd", FlowClass.CONTROL, deadline=45, lifespan=90)
        candidates = transform_candidates(
            control,
            _obs(control, age_ms=20),
            NetworkLink(capacity_bytes_per_tick=560, rtt_ms=160, jitter_ms=25, loss=0.03),
        )
        by_kind = {item.transform.kind: item for item in candidates}

        self.assertFalse(by_kind[TransformKind.CONTROL_INTENT].certificate.feasible)
        self.assertTrue(by_kind[TransformKind.SUPERVISORY_INTENT].certificate.feasible)
        self.assertGreater(
            by_kind[TransformKind.SUPERVISORY_INTENT].certificate.slack_after_wire_ms,
            by_kind[TransformKind.CONTROL_INTENT].certificate.slack_after_wire_ms,
        )

    def test_human_qoe_contract_includes_degraded_transform(self) -> None:
        video = _flow("robot_1:video", FlowClass.HUMAN_QOE, deadline=120, size=4000)
        contract = build_flow_contract(
            video,
            _obs(video, age_ms=30, operator_attention=1.0),
            NetworkLink(capacity_bytes_per_tick=1200, rtt_ms=80, jitter_ms=12, loss=0.01),
        )

        self.assertIsNotNone(contract.transform(TransformKind.DEGRADED))

    def test_semantic_delta_is_certified_as_synthesized_representation(self) -> None:
        state = _flow("robot_1:state", FlowClass.STATE, deadline=120, size=320)
        candidates = transform_candidates(
            state,
            _obs(state, age_ms=100),
            NetworkLink(capacity_bytes_per_tick=756, rtt_ms=120, jitter_ms=15, loss=0.015),
        )
        by_kind = {item.transform.kind: item for item in candidates}

        self.assertFalse(by_kind[TransformKind.RAW].certificate.feasible)
        self.assertTrue(by_kind[TransformKind.SEMANTIC_DELTA].certificate.feasible)
        self.assertLess(
            by_kind[TransformKind.SEMANTIC_DELTA].certificate.predicted_arrival_age_ms,
            by_kind[TransformKind.RAW].certificate.predicted_arrival_age_ms,
        )


def _flow(
    flow_id: str,
    flow_class: FlowClass,
    *,
    deadline: float,
    size: int = 96,
    lifespan: float | None = None,
) -> FlowSpec:
    return FlowSpec(
        flow_id=flow_id,
        robot_id="robot_1",
        topic="/test",
        flow_class=flow_class,
        qos=QoSProfile(deadline_ms=deadline, lifespan_ms=lifespan or deadline * 3),
        qoe=QoEProfile(operator_visible=flow_class is FlowClass.HUMAN_QOE),
        nominal_size_bytes=size,
        nominal_rate_hz=10,
        causal_task_gain=0.8,
    )


def _obs(
    flow: FlowSpec,
    *,
    age_ms: float,
    operator_attention: float = 0.0,
) -> FlowObservation:
    return FlowObservation(
        age_ms=age_ms,
        queue_depth=1,
        measured_loss=0.0,
        measured_rtt_ms=20.0,
        observed_jitter_ms=0.0,
        task=TaskContext(
            task_id="test",
            robot_id=flow.robot_id,
            task_criticality=1.0,
            collision_risk=0.5,
            operator_attention=operator_attention,
            coordination_pressure=0.2,
        ),
    )


if __name__ == "__main__":
    unittest.main()
