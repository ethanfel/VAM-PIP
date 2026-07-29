"""Compact, pose-independent SAM 3D Body proportion signatures.

The native worker imports this module both as a package module and as a
standalone sibling.  Keep it dependency-free: the manager process deliberately
does not depend on NumPy, Torch, or the SAM 3D Body environment.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence


BODY_PROPORTION_MEASUREMENTS = (
    "upperArm",
    "forearm",
    "thigh",
    "shin",
    "torso",
    "shoulderSpan",
    "hipSpan",
)
_PAIRED_MEASUREMENTS = frozenset(
    {"upperArm", "forearm", "thigh", "shin"}
)
_POINT_INDEX = {
    "leftShoulder": 5,
    "rightShoulder": 6,
    "leftElbow": 7,
    "rightElbow": 8,
    "leftHip": 9,
    "rightHip": 10,
    "leftKnee": 11,
    "rightKnee": 12,
    "leftAnkle": 13,
    "rightAnkle": 14,
    "rightWrist": 41,
    "leftWrist": 62,
}
_CONFIDENCE_KIND = "bilateral-geometric-consistency"
_SPACE = "mhr-neutral-bind"


def _finite_number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _point(
    points: Sequence[Sequence[object]],
    name: str,
) -> tuple[float, float, float]:
    try:
        value = points[_POINT_INDEX[name]]
    except (IndexError, KeyError, TypeError) as error:
        raise ValueError("neutral MHR keypoints must contain 70 xyz rows") from error
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("neutral MHR keypoints must contain 70 xyz rows")
    if len(value) != 3:
        raise ValueError("neutral MHR keypoints must contain 70 xyz rows")
    return (
        _finite_number(value[0], label=f"{name}.x"),
        _finite_number(value[1], label=f"{name}.y"),
        _finite_number(value[2], label=f"{name}.z"),
    )


def _distance(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
) -> float:
    return math.sqrt(
        sum((left - right) ** 2 for left, right in zip(first, second))
    )


def _midpoint(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
) -> tuple[float, float, float]:
    return tuple(
        (left + right) * 0.5 for left, right in zip(first, second)
    )  # type: ignore[return-value]


def _rounded(value: float) -> float:
    return round(value, 8)


def _bilateral_confidence(left: float, right: float) -> float:
    """Return a bounded consistency score, not a learned model probability."""

    mean = (left + right) * 0.5
    if mean <= 1e-8:
        return 0.0
    relative_difference = abs(left - right) / mean
    return max(0.0, min(1.0, 1.0 - relative_difference / 0.20))


def _paired_measurement(
    left: float,
    right: float,
    *,
    stature: float,
) -> dict[str, float]:
    mean = (left + right) * 0.5
    return {
        "meters": _rounded(mean),
        "ratio": _rounded(mean / stature),
        "confidence": _rounded(_bilateral_confidence(left, right)),
        "leftMeters": _rounded(left),
        "rightMeters": _rounded(right),
    }


def _single_measurement(
    meters: float,
    *,
    stature: float,
    confidence: float,
) -> dict[str, float]:
    return {
        "meters": _rounded(meters),
        "ratio": _rounded(meters / stature),
        "confidence": _rounded(max(0.0, min(1.0, confidence))),
    }


def derive_body_proportions(
    neutral_keypoints: Sequence[Sequence[object]],
    *,
    stature_m: object,
) -> dict[str, object]:
    """Build a compact signature from neutral-bind MHR geometry.

    ``neutral_keypoints`` must use the fixed MHR70 order. ``stature_m`` is the
    neutral mesh extent along its longitudinal shoulder-to-hip axis, in metres.
    It supplies a scale-independent normalizer while retaining raw values for
    direct comparison with VaM's morphed T-pose skeleton.
    """

    if (
        not isinstance(neutral_keypoints, Sequence)
        or isinstance(neutral_keypoints, (str, bytes))
        or len(neutral_keypoints) != 70
    ):
        raise ValueError("neutral MHR keypoints must contain 70 xyz rows")
    stature = _finite_number(stature_m, label="neutral MHR stature")
    if not 0.25 <= stature <= 4.0:
        raise ValueError("neutral MHR stature is outside the safe human range")

    left_shoulder = _point(neutral_keypoints, "leftShoulder")
    right_shoulder = _point(neutral_keypoints, "rightShoulder")
    left_elbow = _point(neutral_keypoints, "leftElbow")
    right_elbow = _point(neutral_keypoints, "rightElbow")
    left_wrist = _point(neutral_keypoints, "leftWrist")
    right_wrist = _point(neutral_keypoints, "rightWrist")
    left_hip = _point(neutral_keypoints, "leftHip")
    right_hip = _point(neutral_keypoints, "rightHip")
    left_knee = _point(neutral_keypoints, "leftKnee")
    right_knee = _point(neutral_keypoints, "rightKnee")
    left_ankle = _point(neutral_keypoints, "leftAnkle")
    right_ankle = _point(neutral_keypoints, "rightAnkle")

    lengths = {
        "upperArm": (
            _distance(left_shoulder, left_elbow),
            _distance(right_shoulder, right_elbow),
        ),
        "forearm": (
            _distance(left_elbow, left_wrist),
            _distance(right_elbow, right_wrist),
        ),
        "thigh": (
            _distance(left_hip, left_knee),
            _distance(right_hip, right_knee),
        ),
        "shin": (
            _distance(left_knee, left_ankle),
            _distance(right_knee, right_ankle),
        ),
    }
    for name, pair in lengths.items():
        if min(pair) <= 1e-5 or max(pair) >= stature:
            raise ValueError(f"neutral MHR {name} length is invalid")

    paired = {
        name: _paired_measurement(left, right, stature=stature)
        for name, (left, right) in lengths.items()
    }
    shoulder_span = _distance(left_shoulder, right_shoulder)
    hip_span = _distance(left_hip, right_hip)
    torso = _distance(
        _midpoint(left_shoulder, right_shoulder),
        _midpoint(left_hip, right_hip),
    )
    for name, value in (
        ("torso", torso),
        ("shoulderSpan", shoulder_span),
        ("hipSpan", hip_span),
    ):
        if value <= 1e-5 or value >= stature:
            raise ValueError(f"neutral MHR {name} length is invalid")

    arm_confidence = min(
        float(paired["upperArm"]["confidence"]),
        float(paired["forearm"]["confidence"]),
    )
    leg_confidence = min(
        float(paired["thigh"]["confidence"]),
        float(paired["shin"]["confidence"]),
    )
    measurements: dict[str, dict[str, float]] = {
        **paired,
        "torso": _single_measurement(
            torso,
            stature=stature,
            confidence=min(arm_confidence, leg_confidence),
        ),
        "shoulderSpan": _single_measurement(
            shoulder_span,
            stature=stature,
            confidence=arm_confidence,
        ),
        "hipSpan": _single_measurement(
            hip_span,
            stature=stature,
            confidence=leg_confidence,
        ),
    }
    overall_confidence = sum(
        float(measurement["confidence"])
        for measurement in measurements.values()
    ) / len(measurements)
    result: dict[str, object] = {
        "schema": 1,
        "space": _SPACE,
        "normalizer": {
            "id": "stature",
            "meters": _rounded(stature),
        },
        "confidenceKind": _CONFIDENCE_KIND,
        "measurements": measurements,
        "overallConfidence": _rounded(overall_confidence),
    }
    validate_body_proportions(result)
    return result


def _validate_keys(
    value: object,
    expected: Iterable[str],
    *,
    label: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{label} has an invalid schema")
    return value


def validate_body_proportions(value: object) -> None:
    """Strictly validate a serialized body-proportion signature."""

    document = _validate_keys(
        value,
        {
            "schema",
            "space",
            "normalizer",
            "confidenceKind",
            "measurements",
            "overallConfidence",
        },
        label="body proportions",
    )
    if (
        document["schema"] != 1
        or document["space"] != _SPACE
        or document["confidenceKind"] != _CONFIDENCE_KIND
    ):
        raise ValueError("body proportions identity is invalid")
    normalizer = _validate_keys(
        document["normalizer"],
        {"id", "meters"},
        label="body proportions normalizer",
    )
    stature = _finite_number(
        normalizer["meters"],
        label="body proportions stature",
    )
    if normalizer["id"] != "stature" or not 0.25 <= stature <= 4.0:
        raise ValueError("body proportions normalizer is invalid")

    measurements = _validate_keys(
        document["measurements"],
        BODY_PROPORTION_MEASUREMENTS,
        label="body proportions measurements",
    )
    confidences: list[float] = []
    for name in BODY_PROPORTION_MEASUREMENTS:
        paired = name in _PAIRED_MEASUREMENTS
        expected = {"meters", "ratio", "confidence"}
        if paired:
            expected.update({"leftMeters", "rightMeters"})
        measurement = _validate_keys(
            measurements[name],
            expected,
            label=f"body proportions {name}",
        )
        meters = _finite_number(
            measurement["meters"],
            label=f"body proportions {name}.meters",
        )
        ratio = _finite_number(
            measurement["ratio"],
            label=f"body proportions {name}.ratio",
        )
        confidence = _finite_number(
            measurement["confidence"],
            label=f"body proportions {name}.confidence",
        )
        if (
            not 1e-5 < meters < stature
            or not 0.0 < ratio < 1.0
            or abs(ratio - meters / stature) > 2e-7
            or not 0.0 <= confidence <= 1.0
        ):
            raise ValueError(f"body proportions {name} is invalid")
        if paired:
            left = _finite_number(
                measurement["leftMeters"],
                label=f"body proportions {name}.leftMeters",
            )
            right = _finite_number(
                measurement["rightMeters"],
                label=f"body proportions {name}.rightMeters",
            )
            if (
                not 1e-5 < left < stature
                or not 1e-5 < right < stature
                or abs(meters - (left + right) * 0.5) > 2e-7
            ):
                raise ValueError(f"body proportions {name} sides are invalid")
        confidences.append(confidence)

    overall = _finite_number(
        document["overallConfidence"],
        label="body proportions overallConfidence",
    )
    if (
        not 0.0 <= overall <= 1.0
        or abs(overall - sum(confidences) / len(confidences)) > 2e-7
    ):
        raise ValueError("body proportions overallConfidence is invalid")
