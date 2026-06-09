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
from fleetqox.scheduler import CausalSemanticDeadlineScheduler


class SchedulerTest(unittest.TestCase):
    def test_control_is_admitted_before_debug_under_congestion(self) -> None:
        scheduler = CausalSemanticDeadlineScheduler()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 100, 0.9)
        debug = _flow("robot_1:debug", FlowClass.DEBUG, 3000, 0.02)
        candidates = [
            (debug, _obs(debug, age_ms=200)),
            (control, _obs(control, age_ms=60)),
        ]

        decisions = {
            decision.flow_id: decision
            for decision in scheduler.schedule(
                candidates,
                NetworkLink(capacity_bytes_per_tick=500),
            )
        }

        self.assertEqual(decisions[control.flow_id].action, "send")
        self.assertIn(decisions[debug.flow_id].action, {"defer", "send_degraded"})

    def test_stale_sample_is_dropped(self) -> None:
        scheduler = CausalSemanticDeadlineScheduler()
        flow = _flow("robot_1:camera", FlowClass.PERCEPTION, 2000, 0.5)
        decision = scheduler.schedule(
            [(flow, _obs(flow, age_ms=flow.qos.lifespan_ms + 1))],
            NetworkLink(capacity_bytes_per_tick=10_000),
        )[0]

        self.assertEqual(decision.action, "drop")

    def test_qoe_flow_can_be_degraded(self) -> None:
        scheduler = CausalSemanticDeadlineScheduler(degradation_floor=0.2)
        flow = FlowSpec(
            flow_id="robot_1:video",
            robot_id="robot_1",
            topic="/front_camera",
            flow_class=FlowClass.HUMAN_QOE,
            qos=QoSProfile(deadline_ms=120, lifespan_ms=240),
            qoe=QoEProfile(
                operator_visible=True,
                smoothness_weight=1.0,
                freeze_penalty=1.0,
                visual_confidence_weight=1.0,
            ),
            nominal_size_bytes=5000,
            nominal_rate_hz=10,
            causal_task_gain=0.7,
        )

        decision = scheduler.schedule(
            [(flow, _obs(flow, age_ms=80, operator_attention=1.0))],
            NetworkLink(capacity_bytes_per_tick=1200),
        )[0]

        self.assertEqual(decision.action, "send_degraded")
        self.assertTrue(decision.degraded)


def _flow(
    flow_id: str,
    flow_class: FlowClass,
    size: int,
    causal_gain: float,
) -> FlowSpec:
    return FlowSpec(
        flow_id=flow_id,
        robot_id="robot_1",
        topic="/test",
        flow_class=flow_class,
        qos=QoSProfile(deadline_ms=80, lifespan_ms=200),
        qoe=QoEProfile(),
        nominal_size_bytes=size,
        nominal_rate_hz=10,
        causal_task_gain=causal_gain,
    )


def _obs(
    flow: FlowSpec,
    age_ms: float,
    operator_attention: float = 0.0,
) -> FlowObservation:
    return FlowObservation(
        age_ms=age_ms,
        queue_depth=1,
        measured_loss=0.0,
        measured_rtt_ms=20.0,
        observed_jitter_ms=3.0,
        task=TaskContext(
            task_id="test",
            robot_id=flow.robot_id,
            task_criticality=1.0,
            collision_risk=0.6,
            operator_attention=operator_attention,
            coordination_pressure=0.2,
        ),
    )


if __name__ == "__main__":
    unittest.main()
