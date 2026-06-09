"""Stable sample identity signatures for FleetRMW typed projections."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Mapping


PROJECTION_SIGNATURE_VERSION = "fleetrmw.projection_signature.v1"
PROJECTION_SIGNATURE_ALGORITHM = "sha256:canonical_projection_v1"
FLOAT_PRECISION = 6


def projection_signature_record(projection_kind: str, projection_payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "projection_signature_version": PROJECTION_SIGNATURE_VERSION,
        "projection_signature_algorithm": PROJECTION_SIGNATURE_ALGORITHM,
        "projection_signature": projection_signature(projection_kind, projection_payload),
    }


def projection_signature(projection_kind: str, projection_payload: Mapping[str, object]) -> str:
    canonical = canonical_projection_for_signature(projection_kind, projection_payload)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_projection_for_signature(projection_kind: str, projection_payload: Mapping[str, object]) -> dict[str, object]:
    data = _mapping(projection_payload)
    if projection_kind == "typed_twist":
        return {
            "projection_kind": projection_kind,
            "twist": _canonical_twist(data.get("twist")),
        }
    if projection_kind == "typed_odom":
        odom = _mapping(data.get("odometry"))
        pose = _mapping(odom.get("pose"))
        twist = _mapping(odom.get("twist"))
        return {
            "projection_kind": projection_kind,
            "header": _canonical_header(data.get("header")),
            "odometry": {
                "child_frame_id": str(odom.get("child_frame_id", "")),
                "pose": {
                    "position": _canonical_vector(pose.get("position")),
                    "orientation": _canonical_quaternion(pose.get("orientation")),
                    "covariance": _canonical_float_list(pose.get("covariance"), limit=36),
                },
                "twist": {
                    "linear": _canonical_vector(twist.get("linear")),
                    "angular": _canonical_vector(twist.get("angular")),
                    "covariance": _canonical_float_list(twist.get("covariance"), limit=36),
                },
            },
        }
    if projection_kind == "typed_scan":
        scan = _mapping(data.get("scan"))
        return {
            "projection_kind": projection_kind,
            "header": _canonical_header(data.get("header")),
            "scan": {
                "angle_min": _canonical_float(scan.get("angle_min")),
                "angle_max": _canonical_float(scan.get("angle_max")),
                "angle_increment": _canonical_float(scan.get("angle_increment")),
                "time_increment": _canonical_float(scan.get("time_increment")),
                "scan_time": _canonical_float(scan.get("scan_time")),
                "range_min": _canonical_float(scan.get("range_min")),
                "range_max": _canonical_float(scan.get("range_max")),
                "ranges": _canonical_float_list(scan.get("ranges")),
                "intensities": _canonical_float_list(scan.get("intensities")),
            },
        }
    return {
        "projection_kind": projection_kind,
        "payload": _canonical_json_value(data),
    }


def _canonical_header(payload: object) -> dict[str, object]:
    data = _mapping(payload)
    stamp = _mapping(data.get("stamp"))
    return {
        "frame_id": str(data.get("frame_id", "")),
        "stamp": {
            "sec": _int_value(stamp.get("sec")),
            "nanosec": _int_value(stamp.get("nanosec")),
        },
    }


def _canonical_twist(payload: object) -> dict[str, object]:
    data = _mapping(payload)
    return {
        "linear": _canonical_vector(data.get("linear")),
        "angular": _canonical_vector(data.get("angular")),
    }


def _canonical_vector(payload: object) -> dict[str, object]:
    data = _mapping(payload)
    return {
        "x": _canonical_float(data.get("x")),
        "y": _canonical_float(data.get("y")),
        "z": _canonical_float(data.get("z")),
    }


def _canonical_quaternion(payload: object) -> dict[str, object]:
    data = _mapping(payload)
    return {
        "x": _canonical_float(data.get("x")),
        "y": _canonical_float(data.get("y")),
        "z": _canonical_float(data.get("z")),
        "w": _canonical_float(data.get("w"), default=1.0),
    }


def _canonical_float_list(payload: object, *, limit: int | None = None) -> list[object]:
    if not isinstance(payload, list | tuple):
        return []
    values = list(payload[:limit] if limit is not None else payload)
    return [_canonical_float(value) for value in values]


def _canonical_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _canonical_json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, float | int):
        return _canonical_float(value)
    if value is None or isinstance(value, bool | str):
        return value
    return str(value)


def _canonical_float(value: object, *, default: float = 0.0) -> object:
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        numeric = default
    if math.isnan(numeric):
        return "nan"
    if math.isinf(numeric):
        return "inf" if numeric > 0 else "-inf"
    return round(numeric, FLOAT_PRECISION)


def _mapping(value: object) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _int_value(value: object) -> int:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
