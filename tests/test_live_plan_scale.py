import unittest

from fleetqox.live_plan_scale import (
    LivePlanScaleConfig,
    render_live_plan_scale_markdown,
    run_live_plan_scale_probe,
)


class LivePlanScaleTest(unittest.TestCase):
    def test_probe_scales_topic_rules_and_mode_counts(self) -> None:
        summary = run_live_plan_scale_probe(
            LivePlanScaleConfig(robot_count=12, ticks=5, seed=7)
        )

        self.assertEqual(summary["schema_version"], "fleetrmw.live_plan_scale_probe.v1")
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["robot_count"], 12)
        self.assertEqual(summary["topic_count"], 24)
        self.assertEqual(summary["final_rule_count"], 24)
        self.assertEqual(summary["final_mode_counts"]["redundant"], 12)
        self.assertEqual(summary["final_mode_counts"]["unicast"], 12)
        self.assertGreater(summary["decision_ms"]["max"], 0.0)
        self.assertGreater(summary["path_plan_bytes"]["final"], 0)
        preview = ";".join(summary["final_path_plan_preview"])
        self.assertIn("/robot_0000/cmd_vel=backup_5g+primary_wifi", preview)
        self.assertIn("/robot_0000/odom=backup_5g", preview)

    def test_markdown_report_contains_core_metrics(self) -> None:
        summary = run_live_plan_scale_probe(
            LivePlanScaleConfig(robot_count=3, ticks=4, seed=13)
        )
        markdown = render_live_plan_scale_markdown(summary)

        self.assertIn("# Live Plan Scale Probe V1", markdown)
        self.assertIn("Decision p95 ms", markdown)
        self.assertIn("Mode counts", markdown)


if __name__ == "__main__":
    unittest.main()
