import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fleetqox.local_control_lease import (
    ControlLease,
    LeasePolicy,
    LocalControlLeaseState,
    TwistCommand,
    apply_rate_limits,
    clip_command,
    load_lease_policy,
)


class LocalControlLeaseTest(unittest.TestCase):
    def test_accepts_command_under_active_lease(self) -> None:
        state = LocalControlLeaseState()
        state.ingest_lease(_lease(received_ms=100.0, lifespan_ms=90.0))

        decision = state.evaluate_command(TwistCommand(linear_x=0.2, angular_z=0.1), now_ms=120.0)

        self.assertEqual(decision.status, "accept")
        self.assertTrue(decision.publish)
        self.assertEqual(decision.safe_command.linear_x, 0.2)

    def test_clips_command_to_local_bounds(self) -> None:
        state = LocalControlLeaseState(LeasePolicy(max_linear_x=0.25, max_abs_angular_z=0.3))
        state.ingest_lease(_lease(received_ms=100.0, lifespan_ms=90.0))

        decision = state.evaluate_command(TwistCommand(linear_x=0.5, angular_z=-0.8), now_ms=120.0)

        self.assertEqual(decision.status, "clip")
        self.assertTrue(decision.clipped)
        self.assertEqual(decision.safe_command.linear_x, 0.25)
        self.assertEqual(decision.safe_command.angular_z, -0.3)

    def test_fallback_stop_when_lease_expires(self) -> None:
        state = LocalControlLeaseState()
        state.ingest_lease(_lease(received_ms=100.0, lifespan_ms=50.0))

        decision = state.tick(now_ms=151.0)
        repeated = state.tick(now_ms=152.0)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.status, "fallback_stop")
        self.assertTrue(decision.publish)
        self.assertTrue(decision.safe_command.is_zero())
        self.assertIsNone(repeated)

    def test_command_before_lease_is_held_and_replayed_on_lease(self) -> None:
        state = LocalControlLeaseState(LeasePolicy(pending_command_window_ms=120.0))

        missing = state.evaluate_command(TwistCommand(linear_x=0.1), now_ms=100.0)
        replay = state.ingest_lease(_lease(received_ms=150.0, lifespan_ms=80.0))

        self.assertEqual(missing.status, "drop_no_lease")
        self.assertEqual(replay.status, "accept")
        self.assertTrue(replay.publish)
        self.assertEqual(replay.safe_command.linear_x, 0.1)

    def test_duplicate_lease_does_not_extend_active_expiry(self) -> None:
        state = LocalControlLeaseState()
        state.ingest_lease(_lease(event_id=7, received_ms=100.0, lifespan_ms=50.0))

        duplicate = state.ingest_lease(_lease(event_id=7, received_ms=130.0, lifespan_ms=500.0))
        expired = state.tick(now_ms=151.0)

        self.assertEqual(duplicate.status, "duplicate_lease")
        self.assertIsNotNone(expired)
        assert expired is not None
        self.assertEqual(expired.status, "fallback_stop")

    def test_stale_lease_cannot_replace_newer_active_lease(self) -> None:
        state = LocalControlLeaseState()
        state.ingest_lease(_lease(event_id=9, received_ms=100.0, lifespan_ms=500.0))

        stale = state.ingest_lease(_lease(event_id=7, received_ms=130.0, lifespan_ms=500.0))

        self.assertEqual(stale.status, "stale_lease")
        self.assertIsNotNone(state.active_lease)
        assert state.active_lease is not None
        self.assertEqual(state.active_lease.event_id, 9)

    def test_clip_command_zeroes_disallowed_axes(self) -> None:
        safe, clipped = clip_command(
            TwistCommand(linear_x=0.2, linear_y=0.1, angular_x=0.1, angular_z=0.1),
            LeasePolicy(),
        )

        self.assertTrue(clipped)
        self.assertEqual(safe.linear_y, 0.0)
        self.assertEqual(safe.angular_x, 0.0)

    def test_rate_limit_clips_velocity_step(self) -> None:
        state = LocalControlLeaseState(LeasePolicy(max_linear_accel_x=1.0, max_abs_angular_accel_z=2.0))
        state.ingest_lease(_lease(received_ms=100.0, lifespan_ms=500.0))
        state.evaluate_command(TwistCommand(linear_x=0.0, angular_z=0.0), now_ms=120.0)

        decision = state.evaluate_command(TwistCommand(linear_x=0.25, angular_z=0.35), now_ms=220.0)

        self.assertEqual(decision.status, "clip")
        self.assertAlmostEqual(decision.safe_command.linear_x, 0.1)
        self.assertAlmostEqual(decision.safe_command.angular_z, 0.2)
        self.assertIn("acceleration", decision.reason)

    def test_jerk_limit_clips_acceleration_change(self) -> None:
        state = LocalControlLeaseState(
            LeasePolicy(
                max_linear_x=1.0,
                max_linear_accel_x=10.0,
                max_linear_jerk_x=5.0,
                max_abs_angular_jerk_z=100.0,
            )
        )
        state.ingest_lease(_lease(received_ms=100.0, lifespan_ms=500.0))
        state.evaluate_command(TwistCommand(linear_x=0.0), now_ms=100.0)

        decision = state.evaluate_command(TwistCommand(linear_x=0.5), now_ms=200.0)

        self.assertEqual(decision.status, "clip")
        self.assertTrue(decision.clipped)
        self.assertAlmostEqual(decision.safe_command.linear_x, 0.05)
        self.assertIn("jerk", decision.reason)
        self.assertEqual(decision.clip_stages, ("jerk",))

    def test_hold_last_expiry_policy_publishes_previous_output(self) -> None:
        state = LocalControlLeaseState(LeasePolicy(expiry_action="hold_last"))
        state.ingest_lease(_lease(received_ms=100.0, lifespan_ms=50.0))
        state.evaluate_command(TwistCommand(linear_x=0.2, angular_z=0.1), now_ms=120.0)

        decision = state.tick(now_ms=151.0)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.status, "fallback_hold_last")
        self.assertTrue(decision.publish)
        self.assertEqual(decision.safe_command.linear_x, 0.2)

    def test_apply_rate_limits_is_noop_without_previous_timestamp(self) -> None:
        safe, clipped = apply_rate_limits(
            TwistCommand(linear_x=0.25),
            previous=TwistCommand.zero(),
            previous_ms=None,
            now_ms=100.0,
            policy=LeasePolicy(max_linear_accel_x=0.1),
        )

        self.assertFalse(clipped)
        self.assertEqual(safe.linear_x, 0.25)

    def test_loads_profile_from_config(self) -> None:
        policy = load_lease_policy(
            Path("experiments/local_controller_profiles_v1.json"),
            profile_name="warehouse_amr_safe_v1",
        )

        self.assertEqual(policy.controller_profile, "warehouse_amr_safe_v1")
        self.assertEqual(policy.max_linear_x, 0.8)
        self.assertEqual(policy.max_linear_jerk_x, 4.0)
        self.assertEqual(policy.expiry_action, "hold_last")

    def test_profile_override_preserves_selected_profile_name(self) -> None:
        policy = load_lease_policy(
            Path("experiments/local_controller_profiles_v1.json"),
            profile_name="tb4_lite_safe_v1",
            overrides={"max_linear_x": 0.12, "expiry_action": "drop"},
        )

        self.assertEqual(policy.controller_profile, "tb4_lite_safe_v1")
        self.assertEqual(policy.max_linear_x, 0.12)
        self.assertEqual(policy.expiry_action, "drop")

    def test_unknown_profile_fails_clearly(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown lease profile"):
            load_lease_policy(
                Path("experiments/local_controller_profiles_v1.json"),
                profile_name="missing_profile",
            )

    def test_profile_config_rejects_wrong_schema(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "profiles.json"
            path.write_text('{"schema_version":"wrong","profiles":{}}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported profile schema_version"):
                load_lease_policy(path)

    def test_profile_config_rejects_missing_required_field(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "profiles.json"
            profile = _profile_payload()
            del profile["max_linear_jerk_x"]
            path.write_text(json.dumps(_profile_config(profile)), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing fields: max_linear_jerk_x"):
                load_lease_policy(path, profile_name="test_profile")

    def test_profile_config_rejects_negative_value(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "profiles.json"
            profile = _profile_payload()
            profile["max_linear_x"] = -0.1
            path.write_text(json.dumps(_profile_config(profile)), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "field max_linear_x must be positive"):
                load_lease_policy(path, profile_name="test_profile")


def _lease(*, received_ms: float, lifespan_ms: float, event_id: int = 7) -> ControlLease:
    return ControlLease.from_envelope(
        {
            "kind": "supervisory_intent",
            "event_id": event_id,
            "robot_id": "robot_0000",
            "flow_id": "robot_0000:cmd",
            "wire_mode": "supervisory_intent",
            "action": "send_supervisory_intent",
            "source_topic": "/robot_0000/cmd_vel",
            "policy": "fleetqox_semantic_contract_adaptive",
            "deadline_ms": 293.75,
            "lifespan_ms": lifespan_ms,
        },
        received_monotonic_ms=received_ms,
    )


def _profile_payload() -> dict[str, object]:
    return {
        "max_linear_x": 0.25,
        "max_abs_linear_y": 0.0,
        "max_abs_linear_z": 0.0,
        "max_abs_angular_x": 0.0,
        "max_abs_angular_y": 0.0,
        "max_abs_angular_z": 0.35,
        "max_linear_accel_x": 1.0,
        "max_abs_angular_accel_z": 2.0,
        "max_linear_jerk_x": 20.0,
        "max_abs_angular_jerk_z": 40.0,
        "max_local_lifespan_ms": 500.0,
        "pending_command_window_ms": 120.0,
        "expiry_action": "stop",
    }


def _profile_config(profile: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "fleetrmw.local_controller_profiles.v1",
        "default_profile": "test_profile",
        "profiles": {"test_profile": profile},
    }


if __name__ == "__main__":
    unittest.main()
