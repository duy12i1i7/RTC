import unittest

from fleetqox.control_plane import (
    AdaptiveSemanticContractAdmissionController,
    ContextualProfiledLagrangianAdmissionController,
    IntentAwareContextualAdmissionController,
    LagrangianRiskPredictiveAdmissionController,
    PredictiveAdmissionController,
    ProfileAwareLagrangianAdmissionController,
    RiskConstrainedPredictiveAdmissionController,
    RobotBudgetAwareAdmissionController,
    RobotBudgetConfig,
    SemanticContractAdmissionController,
    classify_link_profile,
    control_intent_deadline_ms,
    default_contextual_lagrangian_envelopes,
)
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


class PredictiveAdmissionControllerTest(unittest.TestCase):
    def test_compacts_control_under_pressure(self) -> None:
        controller = PredictiveAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 1000, deadline=45)
        video = _flow(
            "robot_1:video",
            FlowClass.HUMAN_QOE,
            10_000,
            deadline=120,
            operator_visible=True,
        )

        decisions = {
            decision.flow_id: decision
            for decision in controller.schedule(
                [
                    (control, _obs(control, age_ms=20, operator_attention=0.0)),
                    (video, _obs(video, age_ms=20, operator_attention=1.0)),
                ],
                NetworkLink(capacity_bytes_per_tick=700, loss=0.05, jitter_ms=18, rtt_ms=35),
            )
        }

        self.assertEqual(decisions[control.flow_id].action, "send_compacted")
        self.assertEqual(decisions[control.flow_id].wire_mode, "semantic_delta")
        self.assertLess(decisions[control.flow_id].allocated_bytes, control.nominal_size_bytes)

    def test_uses_fresh_best_effort_when_retry_cannot_meet_deadline(self) -> None:
        controller = PredictiveAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)
        decision = controller.schedule(
            [(control, _obs(control, age_ms=35))],
            NetworkLink(capacity_bytes_per_tick=1000, loss=0.12, jitter_ms=12, rtt_ms=40),
        )[0]

        self.assertEqual(decision.reliability, "best_effort_fresh")

    def test_preemptively_drops_stale_opportunistic_flow(self) -> None:
        controller = PredictiveAdmissionController()
        debug = _flow("robot_1:debug", FlowClass.DEBUG, 1800, deadline=1000, lifespan=1000)
        decision = controller.schedule(
            [(debug, _obs(debug, age_ms=900))],
            NetworkLink(capacity_bytes_per_tick=5000),
        )[0]

        self.assertEqual(decision.action, "drop")

    def test_guarded_predictive_drops_control_without_wire_slack(self) -> None:
        controller = RiskConstrainedPredictiveAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)

        decision = controller.schedule(
            [(control, _obs(control, age_ms=35))],
            NetworkLink(capacity_bytes_per_tick=1000, loss=0.08, jitter_ms=20, rtt_ms=60),
        )[0]

        self.assertEqual(decision.action, "drop")
        self.assertEqual(decision.wire_mode, "")
        self.assertIn("deadline-risk guard", decision.reason)

    def test_guarded_predictive_keeps_control_with_sufficient_wire_slack(self) -> None:
        controller = RiskConstrainedPredictiveAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)

        decision = controller.schedule(
            [(control, _obs(control, age_ms=5))],
            NetworkLink(capacity_bytes_per_tick=1000, loss=0.01, jitter_ms=2, rtt_ms=20),
        )[0]

        self.assertIn(decision.action, {"send", "send_compacted"})

    def test_lagrangian_predictive_prefers_compaction_for_risky_control(self) -> None:
        controller = LagrangianRiskPredictiveAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 1000, deadline=45)
        state = _flow("robot_1:state", FlowClass.STATE, 600, deadline=120)

        decisions = {
            decision.flow_id: decision
            for decision in controller.schedule(
                [
                    (control, _obs(control, age_ms=20)),
                    (state, _obs(state, age_ms=20)),
                ],
                NetworkLink(capacity_bytes_per_tick=900, loss=0.05, jitter_ms=12, rtt_ms=35),
            )
        }

        self.assertIn(decisions[control.flow_id].action, {"send_compacted", "defer", "drop"})
        self.assertIn("lagrangian", decisions[control.flow_id].reason)

    def test_lagrangian_multiplier_updates_after_schedule(self) -> None:
        controller = LagrangianRiskPredictiveAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)
        before = controller._deadline_lambda

        controller.schedule(
            [(control, _obs(control, age_ms=20))],
            NetworkLink(capacity_bytes_per_tick=1000, loss=0.08, jitter_ms=20, rtt_ms=60),
        )

        self.assertNotEqual(controller._deadline_lambda, before)

    def test_classifies_link_profiles_from_path_metrics(self) -> None:
        self.assertEqual(
            classify_link_profile(
                NetworkLink(capacity_bytes_per_tick=3600, loss=0.001, jitter_ms=1, rtt_ms=6)
            ),
            "lan",
        )
        self.assertEqual(
            classify_link_profile(
                NetworkLink(capacity_bytes_per_tick=2400, loss=0.01, jitter_ms=5, rtt_ms=40)
            ),
            "wifi",
        )
        self.assertEqual(
            classify_link_profile(
                NetworkLink(capacity_bytes_per_tick=1800, loss=0.015, jitter_ms=15, rtt_ms=120)
            ),
            "wan",
        )
        self.assertEqual(
            classify_link_profile(
                NetworkLink(capacity_bytes_per_tick=1400, loss=0.03, jitter_ms=25, rtt_ms=160)
            ),
            "roaming",
        )

    def test_profile_aware_lagrangian_labels_decision_reason(self) -> None:
        controller = ProfileAwareLagrangianAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)

        decision = controller.schedule(
            [(control, _obs(control, age_ms=20))],
            NetworkLink(capacity_bytes_per_tick=1800, loss=0.015, jitter_ms=15, rtt_ms=120),
        )[0]

        self.assertIn("profile=wan", decision.reason)

    def test_contextual_envelopes_include_safe_balanced_and_utility_arms(self) -> None:
        envelopes = default_contextual_lagrangian_envelopes()

        self.assertEqual(
            [envelope.label for envelope in envelopes["wan"]],
            ["safe", "balanced", "utility"],
        )
        self.assertLess(
            envelopes["wan"][0].config.deadline_risk_budget,
            envelopes["wan"][2].config.deadline_risk_budget,
        )

    def test_contextual_profiled_lagrangian_labels_selected_envelope(self) -> None:
        controller = ContextualProfiledLagrangianAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)
        state = _flow("robot_1:state", FlowClass.STATE, 320, deadline=120)

        decisions = controller.schedule(
            [
                (control, _obs(control, age_ms=20)),
                (state, _obs(state, age_ms=20)),
            ],
            NetworkLink(capacity_bytes_per_tick=1800, loss=0.015, jitter_ms=15, rtt_ms=120),
        )

        self.assertTrue(decisions)
        self.assertTrue(any("profile=wan" in decision.reason for decision in decisions))
        self.assertTrue(any("envelope=" in decision.reason for decision in decisions))
        self.assertGreater(sum(state.pulls for state in controller.states["wan"].values()), 0)

    def test_intent_aware_contextual_sends_control_intent_when_deadline_infeasible(self) -> None:
        controller = IntentAwareContextualAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)

        decision = controller.schedule(
            [(control, _obs(control, age_ms=20))],
            NetworkLink(capacity_bytes_per_tick=756, loss=0.015, jitter_ms=15, rtt_ms=120),
        )[0]

        self.assertEqual(decision.action, "send_intent")
        self.assertEqual(decision.wire_mode, "control_intent")
        self.assertIn("control intent horizon", decision.reason)
        self.assertGreater(
            control_intent_deadline_ms(control, NetworkLink(756, loss=0.015, jitter_ms=15, rtt_ms=120)),
            control.qos.deadline_ms,
        )

    def test_semantic_contract_scheduler_selects_intent_inside_capacity(self) -> None:
        controller = SemanticContractAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)
        state = _flow("robot_1:state", FlowClass.STATE, 600, deadline=120)
        link = NetworkLink(capacity_bytes_per_tick=756, loss=0.015, jitter_ms=15, rtt_ms=120)

        decisions = {
            decision.flow_id: decision
            for decision in controller.schedule(
                [
                    (control, _obs(control, age_ms=20)),
                    (state, _obs(state, age_ms=20)),
                ],
                link,
            )
        }

        self.assertEqual(decisions[control.flow_id].action, "send_intent")
        self.assertEqual(decisions[control.flow_id].wire_mode, "control_intent")
        self.assertLessEqual(
            sum(decision.allocated_bytes for decision in decisions.values()),
            link.capacity_bytes_per_tick,
        )

    def test_semantic_contract_scheduler_uses_raw_when_feasible(self) -> None:
        controller = SemanticContractAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)

        decision = controller.schedule(
            [(control, _obs(control, age_ms=5))],
            NetworkLink(capacity_bytes_per_tick=3000, loss=0.001, jitter_ms=1, rtt_ms=6),
        )[0]

        self.assertEqual(decision.action, "send")
        self.assertEqual(decision.wire_mode, "native")

    def test_semantic_contract_uses_supervisory_intent_when_control_lifespan_is_infeasible(self) -> None:
        controller = SemanticContractAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45, lifespan=90)

        decision = controller.schedule(
            [(control, _obs(control, age_ms=20))],
            NetworkLink(capacity_bytes_per_tick=560, loss=0.03, jitter_ms=25, rtt_ms=160),
        )[0]

        self.assertEqual(decision.action, "send_supervisory_intent")
        self.assertEqual(decision.wire_mode, "supervisory_intent")
        self.assertGreater(decision.predicted_slack_ms, 0.0)

    def test_semantic_contract_loss_shadow_preserves_control_and_caps_state(self) -> None:
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)
        state_flows = [
            _flow(f"robot_1:state{i}", FlowClass.STATE, 320, deadline=120, lifespan=350)
            for i in range(10)
        ]
        candidates = [(control, _obs(control, age_ms=20))] + [
            (state, _obs(state, age_ms=20)) for state in state_flows
        ]

        low_loss = SemanticContractAdmissionController(enable_loss_shadow=True).schedule(
            candidates,
            NetworkLink(capacity_bytes_per_tick=6000, loss=0.015, jitter_ms=20, rtt_ms=120),
        )
        high_loss = SemanticContractAdmissionController(enable_loss_shadow=True).schedule(
            candidates,
            NetworkLink(capacity_bytes_per_tick=6000, loss=0.06, jitter_ms=20, rtt_ms=120),
        )

        high_by_id = {decision.flow_id: decision for decision in high_loss}
        self.assertEqual(high_by_id[control.flow_id].action, "send_intent")
        self.assertLess(
            _sent_non_control(high_loss),
            _sent_non_control(low_loss),
        )
        self.assertTrue(
            any("loss_price=" in decision.reason for decision in high_loss)
        )

    def test_adaptive_semantic_contract_uses_utility_variant_on_stable_lan(self) -> None:
        controller = AdaptiveSemanticContractAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)
        state = _flow("robot_1:state", FlowClass.STATE, 320, deadline=120)

        decisions = controller.schedule(
            [
                (control, _obs(control, age_ms=5)),
                (state, _obs(state, age_ms=5)),
            ],
            NetworkLink(capacity_bytes_per_tick=6000, loss=0.001, jitter_ms=1, rtt_ms=6),
        )

        self.assertTrue(decisions)
        self.assertTrue(
            all("semantic_variant=utility" in decision.reason for decision in decisions)
        )

    def test_adaptive_semantic_contract_keeps_utility_variant_on_nominal_wan(self) -> None:
        controller = AdaptiveSemanticContractAdmissionController()
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)
        state = _flow("robot_1:state", FlowClass.STATE, 320, deadline=120)

        decisions = controller.schedule(
            [
                (control, _obs(control, age_ms=20)),
                (state, _obs(state, age_ms=20)),
            ],
            NetworkLink(capacity_bytes_per_tick=756, loss=0.015, jitter_ms=15, rtt_ms=120),
        )

        self.assertTrue(decisions)
        self.assertTrue(
            all("semantic_variant=utility" in decision.reason for decision in decisions)
        )

    def test_adaptive_semantic_contract_switches_to_tail_shield_under_loss(self) -> None:
        control = _flow("robot_1:cmd", FlowClass.CONTROL, 96, deadline=45)
        state_flows = [
            _flow(f"robot_1:state{i}", FlowClass.STATE, 320, deadline=120, lifespan=350)
            for i in range(10)
        ]
        candidates = [(control, _obs(control, age_ms=20))] + [
            (state, _obs(state, age_ms=20)) for state in state_flows
        ]
        link = NetworkLink(capacity_bytes_per_tick=6000, loss=0.06, jitter_ms=20, rtt_ms=120)

        baseline = SemanticContractAdmissionController().schedule(candidates, link)
        adaptive = AdaptiveSemanticContractAdmissionController().schedule(candidates, link)

        self.assertTrue(
            all("semantic_variant=tail_shield" in decision.reason for decision in adaptive)
        )
        self.assertLessEqual(_sent_non_control(adaptive), _sent_non_control(baseline))
        self.assertEqual(
            {decision.flow_id: decision for decision in adaptive}[control.flow_id].action,
            "send_intent",
        )

    def test_robot_budget_wrapper_promotes_robot_with_control_deficit(self) -> None:
        base = PredictiveAdmissionController()
        controller = RobotBudgetAwareAdmissionController(
            base.schedule,
            config=RobotBudgetConfig(
                min_control_delivery_ratio=1.0,
                max_deadline_risk=0.40,
                critical_gain_scale=1.2,
                control_learning_rate=1.0,
                deadline_learning_rate=0.0,
                deficit_decay=1.0,
            ),
        )
        robot_0_cmd = _flow(
            "robot_0000:cmd",
            FlowClass.CONTROL,
            96,
            deadline=45,
            robot_id="robot_0000",
        )
        robot_1_cmd = _flow(
            "robot_0001:cmd",
            FlowClass.CONTROL,
            96,
            deadline=45,
            robot_id="robot_0001",
        )
        link = NetworkLink(capacity_bytes_per_tick=96, loss=0.01, jitter_ms=2, rtt_ms=20)

        first = {
            decision.flow_id: decision
            for decision in controller.schedule(
                [
                    (robot_0_cmd, _obs(robot_0_cmd, age_ms=10)),
                    (robot_1_cmd, _obs(robot_1_cmd, age_ms=10)),
                ],
                link,
            )
        }
        snapshot_after_first = controller.robot_budget_snapshot()
        second = {
            decision.flow_id: decision
            for decision in controller.schedule(
                [
                    (robot_0_cmd, _obs(robot_0_cmd, age_ms=10)),
                    (robot_1_cmd, _obs(robot_1_cmd, age_ms=10)),
                ],
                link,
            )
        }

        self.assertTrue(first[robot_0_cmd.flow_id].action.startswith("send"))
        self.assertFalse(first[robot_1_cmd.flow_id].action.startswith("send"))
        self.assertGreater(
            snapshot_after_first["robot_0001"]["pressure"],
            snapshot_after_first["robot_0000"]["pressure"],
        )
        self.assertFalse(second[robot_0_cmd.flow_id].action.startswith("send"))
        self.assertTrue(second[robot_1_cmd.flow_id].action.startswith("send"))
        self.assertIn("robot_budget=active", second[robot_1_cmd.flow_id].reason)

    def test_robot_budget_wrapper_reclaims_noncritical_capacity_for_control_floor(self) -> None:
        def base_policy(candidates, _link):
            decisions = []
            for spec, _obs in candidates:
                if spec.flow_class is FlowClass.STATE:
                    decisions.append(
                        FlowDecision(
                            flow_id=spec.flow_id,
                            action="send",
                            priority=10.0,
                            allocated_bytes=96,
                            reason="fake base state",
                            reliability="best_effort",
                            wire_mode="native",
                            predicted_slack_ms=50.0,
                        )
                    )
                else:
                    decisions.append(
                        FlowDecision(
                            flow_id=spec.flow_id,
                            action="defer",
                            priority=0.0,
                            allocated_bytes=0,
                            reason="fake base no control budget",
                        )
                    )
            return decisions

        controller = RobotBudgetAwareAdmissionController(
            base_policy,
            config=RobotBudgetConfig(
                min_control_delivery_ratio=1.0,
                min_control_floor_pressure=0.01,
                control_learning_rate=1.0,
                deadline_learning_rate=0.0,
                deficit_decay=1.0,
            ),
        )
        control = _flow(
            "robot_0001:cmd",
            FlowClass.CONTROL,
            96,
            deadline=45,
            robot_id="robot_0001",
        )
        state = _flow(
            "robot_0001:state",
            FlowClass.STATE,
            96,
            deadline=120,
            robot_id="robot_0001",
        )
        link = NetworkLink(capacity_bytes_per_tick=96, loss=0.01, jitter_ms=2, rtt_ms=20)
        candidates = [
            (control, _obs(control, age_ms=10)),
            (state, _obs(state, age_ms=10)),
        ]

        first = {decision.flow_id: decision for decision in controller.schedule(candidates, link)}
        second = {decision.flow_id: decision for decision in controller.schedule(candidates, link)}

        self.assertEqual(first[control.flow_id].action, "defer")
        self.assertEqual(first[state.flow_id].action, "send")
        self.assertTrue(second[control.flow_id].action.startswith("send"))
        self.assertEqual(second[state.flow_id].action, "defer")
        self.assertIn("control floor", second[control.flow_id].reason)
        self.assertIn("reclaimed capacity", second[state.flow_id].reason)

    def test_robot_budget_n_aware_floor_reserves_control_for_each_robot(self) -> None:
        def base_policy(candidates, _link):
            decisions = []
            sent_state = 0
            for spec, _obs in candidates:
                if spec.flow_class is FlowClass.STATE and sent_state < 4:
                    sent_state += 1
                    decisions.append(
                        FlowDecision(
                            flow_id=spec.flow_id,
                            action="send",
                            priority=10.0,
                            allocated_bytes=96,
                            reason="fake base state",
                            reliability="best_effort",
                            wire_mode="native",
                            predicted_slack_ms=50.0,
                        )
                    )
                else:
                    decisions.append(
                        FlowDecision(
                            flow_id=spec.flow_id,
                            action="defer",
                            priority=0.0,
                            allocated_bytes=0,
                            reason="fake base no control budget",
                        )
                    )
            return decisions

        controller = RobotBudgetAwareAdmissionController(
            base_policy,
            config=RobotBudgetConfig(
                n_aware_control_floor_enabled=True,
                n_aware_control_floor_min_robots=4,
                n_aware_control_floor_pressure=0.10,
                floor_min_intent_bytes=48,
            ),
        )
        candidates = []
        for index in range(8):
            robot_id = f"robot_{index:04d}"
            control = _flow(
                f"{robot_id}:cmd",
                FlowClass.CONTROL,
                96,
                deadline=45,
                robot_id=robot_id,
            )
            state = _flow(
                f"{robot_id}:state",
                FlowClass.STATE,
                96,
                deadline=120,
                robot_id=robot_id,
            )
            candidates.extend(
                [
                    (control, _obs(control, age_ms=10)),
                    (state, _obs(state, age_ms=10)),
                ]
            )

        decisions = {
            decision.flow_id: decision
            for decision in controller.schedule(
                candidates,
                NetworkLink(capacity_bytes_per_tick=8 * 48, loss=0.01, jitter_ms=2, rtt_ms=20),
            )
        }

        control_decisions = [
            decision
            for flow_id, decision in decisions.items()
            if flow_id.endswith(":cmd")
        ]
        state_decisions = [
            decision
            for flow_id, decision in decisions.items()
            if flow_id.endswith(":state")
        ]
        self.assertEqual(len(control_decisions), 8)
        self.assertTrue(all(decision.action.startswith("send") for decision in control_decisions))
        self.assertTrue(all(decision.allocated_bytes <= 48 for decision in control_decisions))
        self.assertTrue(
            all("n_aware_control_floor" in decision.reason for decision in control_decisions)
        )
        self.assertFalse(any(decision.action.startswith("send") for decision in state_decisions))
        self.assertTrue(
            any("reclaimed capacity" in decision.reason for decision in state_decisions)
        )

    def test_robot_budget_wrapper_shapes_noncritical_traffic_from_tail_risk(self) -> None:
        def base_policy(candidates, _link):
            decisions = []
            for spec, _obs in candidates:
                if spec.flow_class is FlowClass.CONTROL:
                    decisions.append(
                        FlowDecision(
                            flow_id=spec.flow_id,
                            action="send_intent",
                            priority=20.0,
                            allocated_bytes=48,
                            reason="fake base control intent",
                            reliability="best_effort_fresh",
                            wire_mode="control_intent",
                            predicted_slack_ms=90.0,
                        )
                    )
                else:
                    decisions.append(
                        FlowDecision(
                            flow_id=spec.flow_id,
                            action="send",
                            priority=2.0,
                            allocated_bytes=spec.nominal_size_bytes,
                            reason="fake base perception",
                            reliability="best_effort",
                            wire_mode="native",
                            predicted_slack_ms=120.0,
                        )
                    )
            return decisions

        controller = RobotBudgetAwareAdmissionController(
            base_policy,
            config=RobotBudgetConfig(
                max_deadline_risk=0.10,
                min_control_delivery_ratio=1.0,
                control_learning_rate=0.0,
                deadline_learning_rate=1.0,
                deficit_decay=1.0,
                pressure_shed_start=0.01,
                deadline_firewall_enabled=False,
            ),
        )
        control = _flow(
            "robot_0001:cmd",
            FlowClass.CONTROL,
            96,
            deadline=45,
            robot_id="robot_0001",
        )
        perception = _flow(
            "robot_0001:scan",
            FlowClass.PERCEPTION,
            800,
            deadline=160,
            robot_id="robot_0001",
        )
        link = NetworkLink(capacity_bytes_per_tick=1400, loss=0.03, jitter_ms=25, rtt_ms=160)
        candidates = [
            (control, _obs(control, age_ms=10)),
            (perception, _obs(perception, age_ms=10)),
        ]

        first = {decision.flow_id: decision for decision in controller.schedule(candidates, link)}
        snapshot = controller.robot_budget_snapshot()
        second = {decision.flow_id: decision for decision in controller.schedule(candidates, link)}

        self.assertEqual(first[perception.flow_id].action, "send")
        self.assertGreater(snapshot["robot_0001"]["pressure"], 0.0)
        self.assertEqual(second[perception.flow_id].action, "send_degraded")
        self.assertLess(second[perception.flow_id].allocated_bytes, first[perception.flow_id].allocated_bytes)
        self.assertIn("pressure_shaping", second[perception.flow_id].reason)
        self.assertIn("robot_budget=active", second[control.flow_id].reason)

    def test_robot_budget_feedback_is_damped_by_sample_window(self) -> None:
        controller = RobotBudgetAwareAdmissionController(
            config=RobotBudgetConfig(
                min_control_delivery_ratio=0.90,
                max_deadline_risk=0.35,
                feedback_learning_scale=0.08,
                feedback_reference_samples=12,
                feedback_deadline_risk_cap=0.55,
                deficit_decay=0.86,
            )
        )

        for _ in range(20):
            controller.apply_feedback_records(
                [
                    {
                        "robot_id": "robot_0001",
                        "control_delivery_ratio": 0.40,
                        "deadline_miss_ratio": 1.0,
                        "feedback_sample_count": 12,
                    }
                ]
            )

        snapshot = controller.robot_budget_snapshot()["robot_0001"]

        self.assertGreater(snapshot["pressure"], 0.0)
        self.assertLess(snapshot["pressure"], 0.45)
        self.assertLessEqual(
            snapshot["deadline_risk_ewma"],
            controller.config.feedback_deadline_risk_cap,
        )

    def test_robot_budget_feedback_sample_count_scales_update(self) -> None:
        low_sample = RobotBudgetAwareAdmissionController(
            config=RobotBudgetConfig(feedback_learning_scale=0.08, feedback_reference_samples=12)
        )
        full_sample = RobotBudgetAwareAdmissionController(
            config=RobotBudgetConfig(feedback_learning_scale=0.08, feedback_reference_samples=12)
        )
        record = {
            "robot_id": "robot_0001",
            "control_delivery_ratio": 0.40,
            "deadline_miss_ratio": 1.0,
        }

        low_sample.apply_feedback_records([record | {"feedback_sample_count": 3}])
        full_sample.apply_feedback_records([record | {"feedback_sample_count": 12}])

        self.assertLess(
            low_sample.robot_budget_snapshot()["robot_0001"]["pressure"],
            full_sample.robot_budget_snapshot()["robot_0001"]["pressure"],
        )

    def test_robot_budget_latency_feedback_adds_shaping_pressure(self) -> None:
        controller = RobotBudgetAwareAdmissionController(
            config=RobotBudgetConfig(
                feedback_learning_scale=1.0,
                feedback_reference_samples=4,
                latency_learning_rate=1.0,
                latency_pressure_gain=1.0,
                max_tail_latency_deadline_ratio=1.0,
                feedback_latency_risk_span=1.0,
            )
        )

        controller.apply_feedback_records(
            [
                {
                    "robot_id": "robot_0001",
                    "tail_latency_ms": 220.0,
                    "mean_deadline_ms": 110.0,
                    "latency_sample_count": 4,
                }
            ]
        )

        snapshot = controller.robot_budget_snapshot()["robot_0001"]
        self.assertEqual(snapshot["service_pressure"], 0.0)
        self.assertGreater(snapshot["latency_deficit"], 0.0)
        self.assertGreater(snapshot["latency_pressure"], 0.0)
        self.assertGreater(snapshot["pressure"], snapshot["service_pressure"])

    def test_robot_budget_latency_pressure_is_control_first(self) -> None:
        controller = RobotBudgetAwareAdmissionController(
            config=RobotBudgetConfig(
                min_control_delivery_ratio=0.90,
                feedback_learning_scale=1.0,
                feedback_reference_samples=4,
                control_learning_rate=1.0,
                latency_learning_rate=1.0,
                latency_pressure_gain=1.0,
                control_first_qoe_margin=0.04,
                max_tail_latency_deadline_ratio=1.0,
                feedback_latency_risk_span=1.0,
            )
        )

        controller.apply_feedback_records(
            [
                {
                    "robot_id": "robot_0001",
                    "control_delivery_ratio": 0.50,
                    "tail_latency_ms": 220.0,
                    "mean_deadline_ms": 110.0,
                    "latency_sample_count": 4,
                }
            ]
        )

        snapshot = controller.robot_budget_snapshot()["robot_0001"]
        self.assertGreater(snapshot["service_pressure"], 0.0)
        self.assertGreater(snapshot["latency_deficit"], 0.0)
        self.assertEqual(snapshot["latency_pressure"], 0.0)
        self.assertEqual(snapshot["pressure"], snapshot["service_pressure"])

    def test_robot_budget_deadline_debt_adds_shaping_pressure(self) -> None:
        controller = RobotBudgetAwareAdmissionController(
            config=RobotBudgetConfig(
                max_deadline_risk=0.30,
                feedback_learning_scale=1.0,
                feedback_reference_samples=4,
                deadline_learning_rate=1.0,
                deadline_shaping_gain=0.50,
            )
        )

        controller.apply_feedback_records(
            [
                {
                    "robot_id": "robot_0001",
                    "deadline_miss_ratio": 0.70,
                    "deadline_sample_count": 4,
                }
            ]
        )

        snapshot = controller.robot_budget_snapshot()["robot_0001"]
        self.assertGreater(snapshot["deadline_deficit"], 0.0)
        self.assertGreater(snapshot["deadline_shaping_pressure"], 0.0)
        self.assertGreater(snapshot["pressure"], snapshot["service_pressure"])

    def test_robot_budget_latency_pressure_shapes_noncritical_only(self) -> None:
        def base_policy(candidates, _link):
            return [
                FlowDecision(
                    flow_id=spec.flow_id,
                    action="send",
                    priority=1.0,
                    allocated_bytes=spec.nominal_size_bytes,
                    reason="base",
                    reliability="best_effort",
                    wire_mode="native",
                    predicted_slack_ms=spec.qos.deadline_ms - obs.age_ms,
                )
                for spec, obs in candidates
            ]

        controller = RobotBudgetAwareAdmissionController(
            base_policy=base_policy,
            config=RobotBudgetConfig(
                feedback_learning_scale=1.0,
                feedback_reference_samples=4,
                latency_learning_rate=1.0,
                latency_pressure_gain=1.0,
                max_tail_latency_deadline_ratio=1.0,
                feedback_latency_risk_span=1.0,
                pressure_shed_start=0.01,
                pressure_shed_max_fraction=1.0,
            ),
        )
        controller.apply_feedback_records(
            [
                {
                    "robot_id": "robot_0001",
                    "tail_latency_ms": 240.0,
                    "mean_deadline_ms": 120.0,
                    "latency_sample_count": 4,
                }
            ]
        )
        control = _flow("robot_0001:cmd", FlowClass.CONTROL, 96, deadline=45, robot_id="robot_0001")
        perception = _flow(
            "robot_0001:scan",
            FlowClass.PERCEPTION,
            800,
            deadline=160,
            robot_id="robot_0001",
        )

        decisions = {
            decision.flow_id: decision
            for decision in controller.schedule(
                [
                    (control, _obs(control, age_ms=8)),
                    (perception, _obs(perception, age_ms=8)),
                ],
                NetworkLink(capacity_bytes_per_tick=1400, loss=0.03, jitter_ms=25, rtt_ms=160),
            )
        }

        self.assertEqual(decisions[control.flow_id].action, "send")
        self.assertNotIn("robot_budget_pressure", control.tags)
        self.assertIn("pressure_shaping", decisions[perception.flow_id].reason)

    def test_deadline_debt_firewall_shapes_noncritical_when_pressure_shed_is_zero(self) -> None:
        def base_policy(candidates, _link):
            return [
                FlowDecision(
                    flow_id=spec.flow_id,
                    action="send",
                    priority=1.0,
                    allocated_bytes=spec.nominal_size_bytes,
                    reason="base",
                    reliability="best_effort",
                    wire_mode="native",
                    predicted_slack_ms=spec.qos.deadline_ms - obs.age_ms,
                )
                for spec, obs in candidates
            ]

        controller = RobotBudgetAwareAdmissionController(
            base_policy=base_policy,
            config=RobotBudgetConfig(
                max_deadline_risk=0.20,
                feedback_learning_scale=1.0,
                feedback_reference_samples=4,
                deadline_learning_rate=1.0,
                pressure_shed_start=0.01,
                pressure_shed_max_fraction=0.0,
                deadline_debt_shed_gain=1.0,
                deadline_debt_shed_max_fraction=1.0,
            ),
        )
        controller.apply_feedback_records(
            [
                {
                    "source": "egress",
                    "robot_id": "robot_0001",
                    "deadline_miss_ratio": 1.0,
                    "deadline_sample_count": 4,
                }
            ]
        )
        control = _flow("robot_0001:cmd", FlowClass.CONTROL, 96, deadline=45, robot_id="robot_0001")
        perception = _flow(
            "robot_0001:scan",
            FlowClass.PERCEPTION,
            800,
            deadline=160,
            robot_id="robot_0001",
        )

        decisions = {
            decision.flow_id: decision
            for decision in controller.schedule(
                [
                    (control, _obs(control, age_ms=8)),
                    (perception, _obs(perception, age_ms=8)),
                ],
                NetworkLink(capacity_bytes_per_tick=1400, loss=0.03, jitter_ms=25, rtt_ms=160),
            )
        }

        self.assertEqual(decisions[control.flow_id].action, "send")
        self.assertIn("pressure_shaping", decisions[perception.flow_id].reason)

    def test_deadline_debt_lifts_control_intent_horizon(self) -> None:
        def base_policy(candidates, _link):
            decisions = []
            for spec, obs in candidates:
                decisions.append(
                    FlowDecision(
                        flow_id=spec.flow_id,
                        action="send_intent",
                        priority=4.0,
                        allocated_bytes=48,
                        reason="base control intent",
                        reliability="best_effort_fresh",
                        wire_mode="control_intent",
                        predicted_slack_ms=spec.qos.deadline_ms - obs.age_ms,
                    )
                )
            return decisions

        controller = RobotBudgetAwareAdmissionController(
            base_policy=base_policy,
            config=RobotBudgetConfig(
                max_deadline_risk=0.20,
                feedback_learning_scale=1.0,
                feedback_reference_samples=4,
                deadline_learning_rate=1.0,
                deadline_horizon_lift_enabled=True,
                deadline_horizon_lift_min_deficit=0.05,
            ),
        )
        controller.apply_feedback_records(
            [
                {
                    "source": "egress",
                    "robot_id": "robot_0001",
                    "deadline_miss_by_transform": {"control:control_intent": 1.0},
                    "deadline_sample_count_by_transform": {"control:control_intent": 4},
                    "feedback_sample_count": 4,
                }
            ]
        )
        control = _flow("robot_0001:cmd", FlowClass.CONTROL, 96, deadline=45, robot_id="robot_0001")

        decision = controller.schedule(
            [(control, _obs(control, age_ms=8))],
            NetworkLink(capacity_bytes_per_tick=1400, loss=0.03, jitter_ms=25, rtt_ms=160),
        )[0]

        self.assertEqual(decision.action, "send_supervisory_intent")
        self.assertEqual(decision.wire_mode, "supervisory_intent")
        self.assertIn("deadline_horizon_lift", decision.reason)

    def test_deadline_firewall_defers_noncontrol_when_tail_exceeds_deadline(self) -> None:
        def base_policy(candidates, _link):
            return [
                FlowDecision(
                    flow_id=spec.flow_id,
                    action="send",
                    priority=1.0,
                    allocated_bytes=spec.nominal_size_bytes,
                    reason="base",
                    reliability="best_effort",
                    wire_mode="native",
                    predicted_slack_ms=spec.qos.deadline_ms - obs.age_ms,
                )
                for spec, obs in candidates
            ]

        controller = RobotBudgetAwareAdmissionController(base_policy=base_policy)
        perception = _flow(
            "robot_0001:scan",
            FlowClass.PERCEPTION,
            800,
            deadline=160,
            robot_id="robot_0001",
        )

        decision = controller.schedule(
            [(perception, _obs(perception, age_ms=8))],
            NetworkLink(capacity_bytes_per_tick=1400, loss=0.03, jitter_ms=25, rtt_ms=160),
        )[0]

        self.assertEqual(decision.action, "defer")
        self.assertIn("deadline_firewall=defer", decision.reason)

    def test_deadline_firewall_reshapes_to_feasible_degraded_representation(self) -> None:
        def base_policy(candidates, _link):
            return [
                FlowDecision(
                    flow_id=spec.flow_id,
                    action="send",
                    priority=1.0,
                    allocated_bytes=spec.nominal_size_bytes,
                    reason="base",
                    reliability="best_effort",
                    wire_mode="native",
                    predicted_slack_ms=spec.qos.deadline_ms - obs.age_ms,
                )
                for spec, obs in candidates
            ]

        controller = RobotBudgetAwareAdmissionController(base_policy=base_policy)
        perception = _flow(
            "robot_0001:scan",
            FlowClass.PERCEPTION,
            5600,
            deadline=160,
            robot_id="robot_0001",
        )

        decision = controller.schedule(
            [(perception, _obs(perception, age_ms=8))],
            NetworkLink(capacity_bytes_per_tick=1400, loss=0.015, jitter_ms=15, rtt_ms=120),
        )[0]

        self.assertEqual(decision.action, "send_degraded")
        self.assertEqual(decision.wire_mode, "degraded")
        self.assertIn("deadline_firewall=reshape", decision.reason)

    def test_deadline_firewall_does_not_rewrite_control_lease(self) -> None:
        def base_policy(candidates, _link):
            return [
                FlowDecision(
                    flow_id=spec.flow_id,
                    action="send_intent",
                    priority=1.0,
                    allocated_bytes=48,
                    reason="base",
                    reliability="best_effort_fresh",
                    wire_mode="control_intent",
                    predicted_slack_ms=spec.qos.deadline_ms - obs.age_ms,
                )
                for spec, obs in candidates
            ]

        controller = RobotBudgetAwareAdmissionController(base_policy=base_policy)
        control = _flow(
            "robot_0001:cmd",
            FlowClass.CONTROL,
            96,
            deadline=45,
            robot_id="robot_0001",
        )

        decision = controller.schedule(
            [(control, _obs(control, age_ms=8))],
            NetworkLink(capacity_bytes_per_tick=1400, loss=0.03, jitter_ms=25, rtt_ms=160),
        )[0]

        self.assertEqual(decision.action, "send_intent")
        self.assertEqual(decision.wire_mode, "control_intent")
        self.assertNotIn("deadline_firewall", decision.reason)

    def test_action_deadline_feedback_tracks_transform_specific_deficit(self) -> None:
        controller = RobotBudgetAwareAdmissionController(
            config=RobotBudgetConfig(
                max_deadline_risk=0.20,
                feedback_learning_scale=1.0,
                feedback_reference_samples=4,
                action_deadline_learning_rate=1.0,
            ),
        )

        controller.apply_feedback_records(
            [
                {
                    "source": "egress",
                    "robot_id": "robot_0001",
                    "deadline_miss_by_transform": {
                        "control:control_intent": 1.0,
                        "control:supervisory_intent": 0.0,
                    },
                    "deadline_sample_count_by_transform": {
                        "control:control_intent": 4,
                        "control:supervisory_intent": 4,
                    },
                    "feedback_sample_count": 4,
                }
            ]
        )

        action_deficits = controller.robot_budget_snapshot()["robot_0001"]["action_deadline_deficits"]

        self.assertGreater(action_deficits["control:control_intent"], 0.0)
        self.assertEqual(action_deficits.get("control:supervisory_intent", 0.0), 0.0)

    def test_local_controller_feedback_owns_control_action_deadline_deficit(self) -> None:
        controller = RobotBudgetAwareAdmissionController(
            config=RobotBudgetConfig(
                max_deadline_risk=0.20,
                feedback_learning_scale=1.0,
                feedback_reference_samples=1,
                action_deadline_learning_rate=1.0,
            ),
        )

        controller.apply_feedback_records(
            [
                {
                    "source": "local_controller",
                    "robot_id": "robot_0001",
                    "flow_class": "control",
                    "action": "send_intent",
                    "wire_mode": "control_intent",
                    "control_delivered": False,
                    "deadline_met": False,
                    "feedback_sample_count": 1,
                }
            ]
        )

        snapshot = controller.robot_budget_snapshot()["robot_0001"]
        action_deficits = snapshot["action_deadline_deficits"]

        self.assertGreater(snapshot["control_deficit"], 0.0)
        self.assertGreater(snapshot["deadline_deficit"], 0.0)
        self.assertGreater(action_deficits["control:control_intent"], 0.0)

    def test_projection_feedback_does_not_credit_service_budget(self) -> None:
        controller = RobotBudgetAwareAdmissionController(
            config=RobotBudgetConfig(
                min_control_delivery_ratio=0.90,
                max_deadline_risk=0.35,
                feedback_learning_scale=1.0,
                feedback_reference_samples=4,
                control_learning_rate=1.0,
                deadline_learning_rate=1.0,
                latency_learning_rate=1.0,
                projection_feedback_latency_weight=1.0,
                deficit_decay=0.80,
            )
        )
        controller.apply_feedback_records(
            [
                {
                    "source": "egress",
                    "robot_id": "robot_0001",
                    "control_delivery_ratio": 0.20,
                    "deadline_miss_ratio": 1.0,
                    "feedback_sample_count": 4,
                }
            ]
        )
        before = controller.robot_budget_snapshot()["robot_0001"]

        controller.apply_feedback_records(
            [
                {
                    "source": "projection_quality_gate",
                    "robot_id": "robot_0001",
                    "flow_class": "perception",
                    "event_type": "projection_quality",
                    "qoe_risk": 0.0,
                    "feedback_sample_count": 4,
                }
            ]
        )
        after = controller.robot_budget_snapshot()["robot_0001"]

        self.assertEqual(after["control_deficit"], before["control_deficit"])
        self.assertEqual(after["deadline_deficit"], before["deadline_deficit"])
        self.assertEqual(after["service_pressure"], before["service_pressure"])

    def test_local_success_credit_is_weaker_than_egress_success_credit(self) -> None:
        config = RobotBudgetConfig(
            min_control_delivery_ratio=0.90,
            max_deadline_risk=0.35,
            feedback_learning_scale=1.0,
            feedback_reference_samples=4,
            control_learning_rate=1.0,
            deadline_learning_rate=1.0,
            local_feedback_success_weight=0.10,
            local_feedback_deadline_success_weight=0.10,
            deficit_decay=0.50,
        )
        egress = RobotBudgetAwareAdmissionController(config=config)
        local = RobotBudgetAwareAdmissionController(config=config)
        failure = {
            "source": "egress",
            "robot_id": "robot_0001",
            "control_delivery_ratio": 0.20,
            "deadline_miss_ratio": 1.0,
            "feedback_sample_count": 4,
        }
        egress.apply_feedback_records([failure])
        local.apply_feedback_records([failure])

        egress.apply_feedback_records(
            [
                {
                    "source": "egress",
                    "robot_id": "robot_0001",
                    "control_delivery_ratio": 1.0,
                    "deadline_miss_ratio": 0.0,
                    "feedback_sample_count": 4,
                }
            ]
        )
        local.apply_feedback_records(
            [
                {
                    "source": "local_controller",
                    "robot_id": "robot_0001",
                    "flow_class": "control",
                    "event_type": "command",
                    "control_delivered": True,
                    "deadline_met": True,
                    "feedback_sample_count": 4,
                }
            ]
        )

        self.assertLess(
            egress.robot_budget_snapshot()["robot_0001"]["service_pressure"],
            local.robot_budget_snapshot()["robot_0001"]["service_pressure"],
        )

    def test_robot_budget_feedback_reports_source_counts(self) -> None:
        controller = RobotBudgetAwareAdmissionController(
            config=RobotBudgetConfig(feedback_learning_scale=1.0, feedback_reference_samples=4)
        )

        result = controller.apply_feedback_records(
            [
                {
                    "source": "egress",
                    "robot_id": "robot_0001",
                    "control_delivery_ratio": 0.50,
                    "feedback_sample_count": 4,
                },
                {
                    "source": "projection_quality_gate",
                    "robot_id": "robot_0001",
                    "qoe_risk": 1.0,
                    "feedback_sample_count": 4,
                },
            ]
        )

        self.assertEqual(result["applied"], 2)
        self.assertEqual(result["sources"], {"egress": 1, "projection_quality_gate": 1})


def _flow(
    flow_id: str,
    flow_class: FlowClass,
    size: int,
    *,
    deadline: float,
    lifespan: float | None = None,
    operator_visible: bool = False,
    robot_id: str = "robot_1",
) -> FlowSpec:
    return FlowSpec(
        flow_id=flow_id,
        robot_id=robot_id,
        topic="/test",
        flow_class=flow_class,
        qos=QoSProfile(deadline_ms=deadline, lifespan_ms=lifespan or deadline * 3),
        qoe=QoEProfile(
            operator_visible=operator_visible,
            smoothness_weight=1.0 if operator_visible else 0.0,
            freeze_penalty=1.0 if operator_visible else 0.0,
            visual_confidence_weight=1.0 if operator_visible else 0.0,
        ),
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
        measured_loss=0.05,
        measured_rtt_ms=30,
        observed_jitter_ms=8,
        task=TaskContext(
            task_id="test",
            robot_id=flow.robot_id,
            task_criticality=1.0,
            collision_risk=0.6,
            operator_attention=operator_attention,
            coordination_pressure=0.3,
        ),
    )


def _sent_non_control(decisions: list) -> int:
    return sum(
        1
        for decision in decisions
        if decision.action.startswith("send")
        and not decision.flow_id.endswith(":cmd")
    )


if __name__ == "__main__":
    unittest.main()
