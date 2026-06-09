import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fleetqox.transport_selector import (
    AdaptiveTransportBindingEstimator,
    BUILTIN_TRANSPORT_OBJECTIVES,
    ProfileObservation,
    TransportBinding,
    TransportBindingManager,
    classify_network_profile,
    render_transport_selection_markdown,
    select_transport_for_profile,
    select_transports_from_paths,
    split_policy_name,
)
from scripts.select_ros2_transport import expand_summary_paths


class TransportSelectorTest(unittest.TestCase):
    def test_teleop_objective_prefers_low_latency_when_control_is_valid(self) -> None:
        summary = _summary(
            "roaming",
            [
                _policy(
                    "data_frame/rmw_zenoh_cpp",
                    utility=120,
                    control_delivery=1.0,
                    deadline_miss=0.0,
                    loss=0.0,
                    latency_p95=30,
                    latency_p99=50,
                ),
                _policy(
                    "event_json/rmw_cyclonedds_cpp",
                    utility=150,
                    control_delivery=1.0,
                    deadline_miss=0.0,
                    loss=0.0,
                    latency_p95=100,
                    latency_p99=140,
                ),
            ],
        )

        selection = select_transport_for_profile(
            summary,
            objective="teleop_latency",
        )

        self.assertEqual(selection["selected_policy"], "data_frame/rmw_zenoh_cpp")
        self.assertEqual(selection["packet_format"], "data_frame")
        self.assertEqual(selection["rmw"], "rmw_zenoh_cpp")

        binding = TransportBinding.from_selection(selection)

        self.assertEqual(binding.profile, "roaming")
        self.assertEqual(binding.packet_format, "data_frame")
        self.assertEqual(binding.as_payload()["policy"], "data_frame/rmw_zenoh_cpp")

    def test_balanced_objective_keeps_utility_tradeoff(self) -> None:
        summary = _summary(
            "wifi",
            [
                _policy(
                    "data_frame/rmw_zenoh_cpp",
                    utility=200,
                    control_delivery=1.0,
                    deadline_miss=0.0,
                    loss=0.0,
                    latency_p95=90,
                    latency_p99=110,
                ),
                _policy(
                    "event_json/rmw_zenoh_cpp",
                    utility=100,
                    control_delivery=1.0,
                    deadline_miss=0.0,
                    loss=0.0,
                    latency_p95=20,
                    latency_p99=40,
                ),
            ],
        )

        selection = select_transport_for_profile(
            summary,
            objective="balanced_safety_utility",
        )

        self.assertEqual(selection["selected_policy"], "data_frame/rmw_zenoh_cpp")

    def test_constraints_exclude_infeasible_candidate(self) -> None:
        summary = _summary(
            "wan",
            [
                _policy(
                    "event_json/rmw_zenoh_cpp",
                    utility=300,
                    control_delivery=0.80,
                    deadline_miss=0.0,
                    loss=0.0,
                    latency_p95=20,
                    latency_p99=40,
                ),
                _policy(
                    "data_frame/rmw_cyclonedds_cpp",
                    utility=180,
                    control_delivery=0.95,
                    deadline_miss=0.0,
                    loss=0.0,
                    latency_p95=60,
                    latency_p99=80,
                ),
            ],
        )

        selection = select_transport_for_profile(summary)
        ranking_by_policy = {row["policy"]: row for row in selection["ranking"]}

        self.assertEqual(
            selection["selected_policy"],
            "data_frame/rmw_cyclonedds_cpp",
        )
        self.assertFalse(ranking_by_policy["event_json/rmw_zenoh_cpp"]["eligible"])
        self.assertLess(ranking_by_policy["event_json/rmw_zenoh_cpp"]["score"], 0.0)

    def test_selector_relaxes_constraints_when_no_candidate_is_feasible(self) -> None:
        summary = _summary(
            "roaming",
            [
                _policy(
                    "event_json/rmw_zenoh_cpp",
                    utility=300,
                    control_delivery=0.70,
                    deadline_miss=0.0,
                    loss=0.0,
                    latency_p95=20,
                    latency_p99=40,
                ),
                _policy(
                    "data_frame/rmw_fastrtps_cpp",
                    utility=100,
                    control_delivery=0.80,
                    deadline_miss=0.0,
                    loss=0.0,
                    latency_p95=80,
                    latency_p99=100,
                ),
            ],
        )

        selection = select_transport_for_profile(summary)

        self.assertTrue(selection["eligible"])
        self.assertTrue(selection["constraint_relaxed"])
        self.assertTrue(selection["constraint_violations"])

    def test_select_from_paths_and_render_markdown(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = (
                Path(tmpdir)
                / "ros2_live_bridge_t3_repeated_packet_wifi_summary.json"
            )
            path.write_text(
                json.dumps(
                    _summary(
                        "wifi",
                        [
                            _policy(
                                "data_frame/rmw_zenoh_cpp",
                                utility=200,
                                control_delivery=1.0,
                                deadline_miss=0.0,
                                loss=0.0,
                                latency_p95=20,
                                latency_p99=40,
                            )
                        ],
                    )
                ),
                encoding="utf-8",
            )

            result = select_transports_from_paths(
                [path],
                objective=BUILTIN_TRANSPORT_OBJECTIVES["balanced_safety_utility"],
            )
            report = render_transport_selection_markdown(result)

        self.assertEqual(result["selections"][0]["profile"], "wifi")
        self.assertEqual(result["bindings"][0]["packet_format"], "data_frame")
        self.assertIn("Selected Policies", report)
        self.assertIn("data_frame/rmw_zenoh_cpp", report)

    def test_split_policy_name_and_expand_summary_globs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            one = root / "one_summary.json"
            two = root / "two_summary.json"
            one.write_text("{}", encoding="utf-8")
            two.write_text("{}", encoding="utf-8")

            paths = expand_summary_paths([str(root / "*_summary.json")])

        self.assertEqual(
            split_policy_name("event_json/rmw_zenoh_cpp"),
            ("event_json", "rmw_zenoh_cpp"),
        )
        self.assertEqual(split_policy_name("custom"), ("unknown", "custom"))
        self.assertEqual(
            [path.name for path in paths],
            ["one_summary.json", "two_summary.json"],
        )

    def test_binding_manager_classifies_runtime_link_profiles(self) -> None:
        self.assertEqual(
            classify_network_profile(
                ProfileObservation(
                    capacity_bytes_per_second=125_000,
                    rtt_ms=35,
                    jitter_ms=5,
                    loss=0.005,
                )
            ),
            "wifi",
        )
        self.assertEqual(
            classify_network_profile(
                ProfileObservation(
                    capacity_bytes_per_second=90_000,
                    rtt_ms=90,
                    jitter_ms=15,
                    loss=0.015,
                )
            ),
            "wan",
        )
        self.assertEqual(
            classify_network_profile(
                ProfileObservation(
                    capacity_bytes_per_second=70_000,
                    rtt_ms=160,
                    jitter_ms=25,
                    loss=0.03,
                )
            ),
            "roaming",
        )

    def test_binding_manager_selects_binding_from_link_payload(self) -> None:
        result = {
            "bindings": [
                _binding("wifi", "data_frame/rmw_zenoh_cpp"),
                _binding("wan", "event_json/rmw_zenoh_cpp"),
                _binding("roaming", "event_json/rmw_cyclonedds_cpp"),
            ]
        }
        manager = TransportBindingManager(result)

        binding = manager.binding_for_link_payload(
            {
                "capacity_bytes_per_tick": 1800,
                "rtt_ms": 90,
                "jitter_ms": 15,
                "loss": 0.015,
            }
        )

        self.assertEqual(binding.profile, "wan")
        self.assertEqual(binding.policy, "event_json/rmw_zenoh_cpp")

    def test_binding_manager_selects_by_profile_and_objective(self) -> None:
        manager = TransportBindingManager(
            {
                "bindings": [
                    _binding(
                        "wan",
                        "event_json/rmw_zenoh_cpp",
                        objective="balanced_safety_utility",
                    ),
                    _binding(
                        "wan",
                        "data_frame/rmw_cyclonedds_cpp",
                        objective="autonomy_safety",
                    ),
                ]
            }
        )

        balanced = manager.binding_for_profile(
            "wan",
            objective="balanced_safety_utility",
        )
        autonomy = manager.binding_for_link_payload(
            {
                "capacity_bytes_per_tick": 1800,
                "rtt_ms": 90,
                "jitter_ms": 15,
                "loss": 0.015,
            },
            objective="autonomy_safety",
        )

        self.assertEqual(balanced.policy, "event_json/rmw_zenoh_cpp")
        self.assertEqual(autonomy.policy, "data_frame/rmw_cyclonedds_cpp")

    def test_adaptive_estimator_smooths_and_hysteresis_switches_profile(self) -> None:
        manager = TransportBindingManager(
            {
                "bindings": [
                    _binding("wifi", "data_frame/rmw_zenoh_cpp"),
                    _binding("wan", "event_json/rmw_zenoh_cpp"),
                    _binding("roaming", "event_json/rmw_cyclonedds_cpp"),
                ]
            }
        )
        estimator = manager.adaptive_estimator(
            smoothing_alpha=1.0,
            hysteresis_margin=0.05,
            min_dwell_ticks=2,
        )

        first = estimator.update(
            ProfileObservation(
                capacity_bytes_per_second=120_000,
                rtt_ms=40,
                jitter_ms=5,
                loss=0.01,
            )
        )
        second = estimator.update(
            ProfileObservation(
                capacity_bytes_per_second=70_000,
                rtt_ms=160,
                jitter_ms=25,
                loss=0.03,
            )
        )
        third = estimator.update(
            ProfileObservation(
                capacity_bytes_per_second=70_000,
                rtt_ms=160,
                jitter_ms=25,
                loss=0.03,
            )
        )
        fourth = estimator.update(
            ProfileObservation(
                capacity_bytes_per_second=70_000,
                rtt_ms=160,
                jitter_ms=25,
                loss=0.03,
            )
        )

        self.assertEqual(first.binding.profile, "wifi")
        self.assertEqual(second.binding.profile, "wifi")
        self.assertEqual(third.binding.profile, "wifi")
        self.assertEqual(fourth.binding.profile, "roaming")
        self.assertTrue(fourth.estimate.changed)

    def test_adaptive_estimator_can_update_from_link_payload(self) -> None:
        manager = TransportBindingManager(
            {
                "bindings": [
                    _binding("wifi", "data_frame/rmw_zenoh_cpp"),
                    _binding("wan", "event_json/rmw_zenoh_cpp"),
                ]
            }
        )
        estimator = AdaptiveTransportBindingEstimator(
            manager,
            prototypes=manager.prototypes,
            smoothing_alpha=1.0,
        )

        decision = estimator.update_from_link_payload(
            {
                "capacity_bytes_per_tick": 1800,
                "rtt_ms": 90,
                "jitter_ms": 15,
                "loss": 0.015,
            }
        )

        self.assertEqual(decision.binding.profile, "wan")
        self.assertGreater(decision.estimate.confidence, 0.0)


def _summary(profile: str, policies: list[dict[str, object]]) -> dict[str, object]:
    return {
        "records": len(policies),
        "policies": policies,
        "pareto_frontier": [policy["policy"] for policy in policies[:1]],
        "profiles": [
            {
                "profile": profile,
                "config": {
                    "capacity_bytes_per_second": 100000,
                    "delay_ms": 10,
                    "jitter_ms": 2,
                    "loss_percent": 0.5,
                },
            }
        ],
    }


def _policy(
    policy: str,
    *,
    utility: float,
    control_delivery: float,
    deadline_miss: float,
    loss: float,
    latency_p95: float,
    latency_p99: float,
) -> dict[str, object]:
    return {
        "policy": policy,
        "runs": 3,
        "semantic_utility_delivered_mean": utility,
        "control_delivery_ratio_mean": control_delivery,
        "control_starvation_events_mean": 0.0,
        "control_non_delivery_events_mean": 0.0,
        "deadline_miss_ratio_mean": deadline_miss,
        "loss_ratio_mean": loss,
        "latency_p95_ms_mean": latency_p95,
        "latency_p99_ms_mean": latency_p99,
        "rx_mean": utility / 5.0,
        "bytes_rx_mean": utility * 100.0,
    }


def _binding(
    profile: str,
    policy: str,
    *,
    objective: str = "balanced_safety_utility",
) -> dict[str, object]:
    packet_format, rmw = split_policy_name(policy)
    return {
        "profile": profile,
        "objective": objective,
        "policy": policy,
        "packet_format": packet_format,
        "rmw": rmw,
        "score": 1.0,
    }


if __name__ == "__main__":
    unittest.main()
