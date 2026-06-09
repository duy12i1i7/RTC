import unittest

from fleetqox.projection_identity import (
    PROJECTION_SIGNATURE_ALGORITHM,
    PROJECTION_SIGNATURE_VERSION,
    projection_signature,
    projection_signature_record,
)


class ProjectionIdentityTest(unittest.TestCase):
    def test_signature_record_has_stable_metadata(self) -> None:
        record = projection_signature_record("typed_scan", _scan_payload())

        self.assertEqual(record["projection_signature_version"], PROJECTION_SIGNATURE_VERSION)
        self.assertEqual(record["projection_signature_algorithm"], PROJECTION_SIGNATURE_ALGORITHM)
        self.assertRegex(str(record["projection_signature"]), r"^[0-9a-f]{64}$")

    def test_scan_signature_ignores_non_ros_projection_metadata(self) -> None:
        with_metadata = _scan_payload() | {"scan": _scan_payload()["scan"] | {"source_sample_count": 6, "downsample_stride": 2}}

        self.assertEqual(
            projection_signature("typed_scan", _scan_payload()),
            projection_signature("typed_scan", with_metadata),
        )

    def test_signature_tolerates_float32_rounding(self) -> None:
        payload = _scan_payload()
        rounded_like_ros = _scan_payload() | {
            "scan": _scan_payload()["scan"]
            | {
                "angle_increment": 0.10000000149011612,
                "ranges": [1.0, 1.100000023841858, 1.2000000476837158],
            }
        }

        self.assertEqual(
            projection_signature("typed_scan", payload),
            projection_signature("typed_scan", rounded_like_ros),
        )


def _scan_payload() -> dict[str, object]:
    return {
        "header": {"frame_id": "robot_0000/base_scan", "stamp": {"sec": 1, "nanosec": 2}},
        "scan": {
            "angle_min": -1.0,
            "angle_max": 1.0,
            "angle_increment": 0.1,
            "time_increment": 0.0,
            "scan_time": 0.0,
            "range_min": 0.12,
            "range_max": 8.0,
            "ranges": [1.0, 1.1, 1.2],
            "intensities": [],
        },
    }


if __name__ == "__main__":
    unittest.main()
