import unittest
from types import SimpleNamespace

from fleetqox.projection_identity import projection_signature
from scripts.run_ros2_projection_quality_gate import (
    laser_scan_from_projection_payload,
    odometry_from_projection_payload,
    projection_signature_for_laser_scan_message,
    projection_signature_for_odometry_message,
)


class ProjectionQualityGateAdapterTest(unittest.TestCase):
    def test_reconstructs_odometry_from_projection_payload(self) -> None:
        message = odometry_from_projection_payload(FakeOdometry, _odom_projection_payload())

        self.assertEqual(message.header.frame_id, "odom")
        self.assertEqual(message.header.stamp.sec, 1)
        self.assertEqual(message.header.stamp.nanosec, 2)
        self.assertEqual(message.child_frame_id, "robot_0000")
        self.assertEqual(message.pose.pose.position.x, 1.2)
        self.assertEqual(message.pose.pose.orientation.w, 0.99)
        self.assertEqual(message.twist.twist.linear.x, 0.2)
        self.assertEqual(message.twist.twist.angular.z, 0.1)
        self.assertEqual(
            projection_signature_for_odometry_message(message),
            projection_signature("typed_odom", _odom_projection_payload()),
        )

    def test_reconstructs_laser_scan_from_projection_payload(self) -> None:
        message = laser_scan_from_projection_payload(FakeLaserScan, _scan_projection_payload())

        self.assertEqual(message.header.frame_id, "robot_0000/base_scan")
        self.assertEqual(message.angle_min, -1.0)
        self.assertEqual(message.angle_max, 1.0)
        self.assertEqual(message.range_min, 0.12)
        self.assertEqual(message.range_max, 8.0)
        self.assertEqual(message.ranges, [1.0, 1.1, 1.2])
        self.assertEqual(
            projection_signature_for_laser_scan_message(message),
            projection_signature("typed_scan", _scan_projection_payload()),
        )

    def test_rejects_missing_projection_payload_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing odometry"):
            odometry_from_projection_payload(FakeOdometry, {"kind": "typed_odom"})

        with self.assertRaisesRegex(ValueError, "missing scan"):
            laser_scan_from_projection_payload(FakeLaserScan, {"kind": "typed_scan"})


class FakeOdometry:
    def __init__(self) -> None:
        self.header = _header()
        self.child_frame_id = ""
        self.pose = SimpleNamespace(
            pose=SimpleNamespace(position=_vector(), orientation=_quaternion()),
            covariance=[0.0] * 36,
        )
        self.twist = SimpleNamespace(
            twist=SimpleNamespace(linear=_vector(), angular=_vector()),
            covariance=[0.0] * 36,
        )


class FakeLaserScan:
    def __init__(self) -> None:
        self.header = _header()
        self.angle_min = 0.0
        self.angle_max = 0.0
        self.angle_increment = 0.0
        self.time_increment = 0.0
        self.scan_time = 0.0
        self.range_min = 0.0
        self.range_max = 0.0
        self.ranges = []
        self.intensities = []


def _header() -> SimpleNamespace:
    return SimpleNamespace(stamp=SimpleNamespace(sec=0, nanosec=0), frame_id="")


def _vector() -> SimpleNamespace:
    return SimpleNamespace(x=0.0, y=0.0, z=0.0)


def _quaternion() -> SimpleNamespace:
    return SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0)


def _odom_projection_payload() -> dict[str, object]:
    return {
        "schema_version": "fleetrmw.typed_projection.v1",
        "kind": "typed_odom",
        "event_id": 7,
        "header": {"frame_id": "odom", "stamp": {"sec": 1, "nanosec": 2}},
        "odometry": {
            "child_frame_id": "robot_0000",
            "pose": {
                "position": {"x": 1.2, "y": 0.3, "z": 0.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.1, "w": 0.99},
                "covariance": [0.0] * 36,
            },
            "twist": {
                "linear": {"x": 0.2, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.1},
                "covariance": [0.0] * 36,
            },
        },
    }


def _scan_projection_payload() -> dict[str, object]:
    return {
        "schema_version": "fleetrmw.typed_projection.v1",
        "kind": "typed_scan",
        "event_id": 8,
        "header": {"frame_id": "robot_0000/base_scan", "stamp": {"sec": 1, "nanosec": 2}},
        "scan": {
            "angle_min": -1.0,
            "angle_max": 1.0,
            "angle_increment": 0.1,
            "range_min": 0.12,
            "range_max": 8.0,
            "ranges": [1.0, 1.1, 1.2],
            "intensities": [],
        },
    }


if __name__ == "__main__":
    unittest.main()
