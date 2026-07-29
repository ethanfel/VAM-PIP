from __future__ import annotations

import math
import re
from typing import Iterable


BODY_PROPORTION_SCHEMA = 1
BODY_PROPORTION_METRICS = (
    "upperArm",
    "forearm",
    "thigh",
    "shin",
    "torso",
    "shoulderSpan",
    "hipSpan",
)
BODY_PROPORTION_REGIONS = frozenset({"arms", "legs", "torso", "widths"})
_OPAQUE_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_METRIC_PRESENTATION = {
    "upperArm": ("Upper arm", "arms"),
    "forearm": ("Forearm", "arms"),
    "thigh": ("Thigh", "legs"),
    "shin": ("Shin", "legs"),
    "torso": ("Torso", "torso"),
    "shoulderSpan": ("Shoulder span", "widths"),
    "hipSpan": ("Hip span", "widths"),
}
_KEYPOINT_SEGMENTS = {
    "upperArm": (
        ("left-shoulder", "left-elbow"),
        ("right-shoulder", "right-elbow"),
    ),
    "forearm": (
        ("left-elbow", "left-wrist"),
        ("right-elbow", "right-wrist"),
    ),
    "thigh": (
        ("left-hip", "left-knee"),
        ("right-hip", "right-knee"),
    ),
    "shin": (
        ("left-knee", "left-ankle"),
        ("right-knee", "right-ankle"),
    ),
}

# These are intentionally approximate response scales, not claims about a
# Genesis morph's physical units. The narrow per-apply bound below keeps the
# first pass conservative until a live per-character calibration is available.
_MORPH_TARGETS = (
    {
        "region": "arms",
        "names": ("Arms Short",),
        "metrics": ("upperArm", "forearm"),
        "fraction_per_value": -0.20,
    },
    {
        "region": "legs",
        "names": ("Legs Length", "Lower Body Length"),
        "metrics": ("thigh", "shin"),
        "fraction_per_value": 0.20,
    },
    {
        "region": "torso",
        "names": ("Upper Body Length", "Upper Torso Length"),
        "metrics": ("torso",),
        "fraction_per_value": 0.20,
    },
    {
        "region": "widths",
        "names": ("Shoulder Width", "Shoulder Width (B)"),
        "metrics": ("shoulderSpan",),
        "fraction_per_value": 0.20,
    },
)
_MAX_VALUE_CHANGE = 0.25
_MAX_RATIO_CHANGE = 0.15
_MIN_RATIO_CHANGE = 0.015


def _finite_number(
    value: object,
    *,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    if minimum is not None and result < minimum:
        raise ValueError(f"{label} is below its supported range")
    if maximum is not None and result > maximum:
        raise ValueError(f"{label} exceeds its supported range")
    return result


def _point(value: object, *, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label} must contain three coordinates")
    return tuple(
        _finite_number(item, label=label, minimum=-100.0, maximum=100.0)
        for item in value
    )  # type: ignore[return-value]


def _distance(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def _midpoint(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
) -> tuple[float, float, float]:
    return tuple((a + b) * 0.5 for a, b in zip(first, second))  # type: ignore[return-value]


def _bilateral_confidence(left: float, right: float) -> float:
    mean = (left + right) * 0.5
    if mean <= 1e-8:
        return 0.0
    disagreement = abs(left - right) / mean
    return max(0.15, min(0.9, 0.9 - disagreement * 1.8))


def _measurement(
    meters: float,
    confidence: float,
    *,
    left: float | None = None,
    right: float | None = None,
) -> dict[str, float]:
    result = {
        "meters": meters,
        "confidence": max(0.0, min(1.0, confidence)),
    }
    if left is not None:
        result["leftMeters"] = left
    if right is not None:
        result["rightMeters"] = right
    return result


def _structural_length(measurements: dict[str, dict[str, float]]) -> float:
    return (
        measurements["torso"]["meters"]
        + measurements["thigh"]["meters"]
        + measurements["shin"]["meters"]
    )


def _finalize_signature(
    measurements: dict[str, dict[str, float]],
    *,
    space: str,
    overall_confidence: float | None = None,
) -> dict[str, object]:
    if set(measurements) != set(BODY_PROPORTION_METRICS):
        raise ValueError("body-proportion measurements are incomplete")
    normalizer = _structural_length(measurements)
    if not math.isfinite(normalizer) or normalizer <= 1e-6:
        raise ValueError("body-proportion structural length is invalid")
    normalized: dict[str, dict[str, float]] = {}
    confidences: list[float] = []
    for metric in BODY_PROPORTION_METRICS:
        item = dict(measurements[metric])
        meters = _finite_number(
            item.get("meters"),
            label=f"{metric}.meters",
            minimum=1e-6,
            maximum=10.0,
        )
        confidence = _finite_number(
            item.get("confidence", 0.5),
            label=f"{metric}.confidence",
            minimum=0.0,
            maximum=1.0,
        )
        item["meters"] = meters
        item["ratio"] = meters / normalizer
        item["confidence"] = confidence
        normalized[metric] = item
        confidences.append(confidence)
    if overall_confidence is None:
        overall_confidence = sum(confidences) / len(confidences)
    else:
        overall_confidence = _finite_number(
            overall_confidence,
            label="overallConfidence",
            minimum=0.0,
            maximum=1.0,
        )
    return {
        "schema": BODY_PROPORTION_SCHEMA,
        "space": space,
        "normalizer": {
            "id": "structural-length",
            "meters": normalizer,
        },
        "measurements": normalized,
        "overallConfidence": overall_confidence,
    }


def _validated_embedded_signature(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict) or value.get("schema") != BODY_PROPORTION_SCHEMA:
        return None
    raw_measurements = value.get("measurements")
    if not isinstance(raw_measurements, dict):
        return None
    measurements: dict[str, dict[str, float]] = {}
    try:
        for metric in BODY_PROPORTION_METRICS:
            raw = raw_measurements.get(metric)
            if not isinstance(raw, dict):
                return None
            item = _measurement(
                _finite_number(
                    raw.get("meters"),
                    label=f"{metric}.meters",
                    minimum=1e-6,
                    maximum=10.0,
                ),
                _finite_number(
                    raw.get("confidence", 0.5),
                    label=f"{metric}.confidence",
                    minimum=0.0,
                    maximum=1.0,
                ),
            )
            for side in ("leftMeters", "rightMeters"):
                if side in raw:
                    item[side] = _finite_number(
                        raw[side],
                        label=f"{metric}.{side}",
                        minimum=1e-6,
                        maximum=10.0,
                    )
            measurements[metric] = item
        return _finalize_signature(
            measurements,
            space=str(value.get("space") or "mhr-neutral-bind")[:64],
            overall_confidence=value.get("overallConfidence"),
        )
    except ValueError:
        return None


def signature_from_manifest(
    manifest: dict[str, object],
    person_index: int,
) -> dict[str, object]:
    """Return a compact, pose-independent-ish body signature.

    New workers publish a neutral MHR signature. Older completed jobs remain
    usable through distances between named rigid anatomical landmarks.
    """

    if isinstance(person_index, bool) or not isinstance(person_index, int):
        raise TypeError("person_index must be an integer")
    people = manifest.get("people")
    if (
        not isinstance(people, list)
        or person_index < 0
        or person_index >= len(people)
        or not isinstance(people[person_index], dict)
    ):
        raise ValueError("person_index is not available in this SAM3D result")
    person = people[person_index]
    embedded = _validated_embedded_signature(person.get("bodyProportions"))
    if embedded is not None:
        return embedded

    names = person.get("keypointNames")
    values = person.get("keypoints3d")
    if (
        not isinstance(names, list)
        or not isinstance(values, list)
        or len(names) != len(values)
    ):
        raise ValueError("SAM3D body landmarks are unavailable")
    points: dict[str, tuple[float, float, float]] = {}
    for index, (name, value) in enumerate(zip(names, values)):
        if not isinstance(name, str) or name in points:
            raise ValueError("SAM3D body landmark names are invalid")
        points[name] = _point(value, label=f"keypoints3d[{index}]")

    required = {
        "left-shoulder",
        "right-shoulder",
        "left-elbow",
        "right-elbow",
        "left-wrist",
        "right-wrist",
        "left-hip",
        "right-hip",
        "left-knee",
        "right-knee",
        "left-ankle",
        "right-ankle",
        "neck",
    }
    if not required.issubset(points):
        raise ValueError("SAM3D body landmarks are incomplete")

    measurements: dict[str, dict[str, float]] = {}
    for metric, ((left_a, left_b), (right_a, right_b)) in _KEYPOINT_SEGMENTS.items():
        left = _distance(points[left_a], points[left_b])
        right = _distance(points[right_a], points[right_b])
        measurements[metric] = _measurement(
            (left + right) * 0.5,
            _bilateral_confidence(left, right),
            left=left,
            right=right,
        )
    pelvis = _midpoint(points["left-hip"], points["right-hip"])
    measurements["torso"] = _measurement(
        _distance(pelvis, points["neck"]),
        0.62,
    )
    measurements["shoulderSpan"] = _measurement(
        _distance(points["left-shoulder"], points["right-shoulder"]),
        0.48,
    )
    measurements["hipSpan"] = _measurement(
        _distance(points["left-hip"], points["right-hip"]),
        0.42,
    )
    return _finalize_signature(
        measurements,
        space="mhr-landmark-distance-fallback",
    )


def signature_from_live(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("VaM body-proportion measurements are unavailable")
    raw_measurements = value.get("measurements")
    if not isinstance(raw_measurements, dict):
        raise ValueError("VaM body-proportion measurements are unavailable")
    measurements: dict[str, dict[str, float]] = {}
    for metric in BODY_PROPORTION_METRICS:
        raw = raw_measurements.get(metric)
        if isinstance(raw, dict):
            meters_value = raw.get("meters")
            confidence_value = raw.get("confidence", 1.0)
        else:
            meters_value = raw
            confidence_value = 1.0
        measurements[metric] = _measurement(
            _finite_number(
                meters_value,
                label=f"VaM {metric}",
                minimum=1e-6,
                maximum=10.0,
            ),
            _finite_number(
                confidence_value,
                label=f"VaM {metric} confidence",
                minimum=0.0,
                maximum=1.0,
            ),
        )
    return _finalize_signature(measurements, space="vam-live-skeleton")


def normalize_regions(value: object) -> frozenset[str]:
    if value is None:
        return BODY_PROPORTION_REGIONS
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise TypeError("regions must be a list")
    regions: set[str] = set()
    for item in value:
        if not isinstance(item, str) or item not in BODY_PROPORTION_REGIONS:
            raise ValueError("regions contains an unsupported body region")
        regions.add(item)
    return frozenset(regions)


def normalize_strength(value: object) -> float:
    return _finite_number(
        value,
        label="strength",
        minimum=0.0,
        maximum=1.0,
    )


def _live_morphs(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in value[:64]:
        if not isinstance(raw, dict):
            continue
        key = raw.get("key")
        name = raw.get("name")
        if (
            not isinstance(key, str)
            or _OPAQUE_TOKEN.fullmatch(key) is None
            or key in seen
            or not isinstance(name, str)
            or not 1 <= len(name) <= 128
        ):
            continue
        try:
            current = _finite_number(
                raw.get("value"),
                label="morph value",
                minimum=-100.0,
                maximum=100.0,
            )
            minimum = _finite_number(
                raw.get("min"),
                label="morph minimum",
                minimum=-100.0,
                maximum=100.0,
            )
            maximum = _finite_number(
                raw.get("max"),
                label="morph maximum",
                minimum=-100.0,
                maximum=100.0,
            )
        except ValueError:
            continue
        if minimum > maximum or current < minimum - 1e-5 or current > maximum + 1e-5:
            continue
        seen.add(key)
        result.append(
            {
                "key": key,
                "name": name,
                "region": str(raw.get("region") or "")[:128],
                "value": current,
                "min": minimum,
                "max": maximum,
            }
        )
    return result


def _combined_ratio(
    signature: dict[str, object],
    metrics: Iterable[str],
) -> tuple[float, float]:
    raw = signature["measurements"]
    assert isinstance(raw, dict)
    items = [raw[metric] for metric in metrics]
    assert all(isinstance(item, dict) for item in items)
    ratio = sum(float(item["ratio"]) for item in items)  # type: ignore[index]
    confidence = min(float(item["confidence"]) for item in items)  # type: ignore[index]
    return ratio, confidence


def build_analysis(
    target: dict[str, object],
    live: dict[str, object],
    body_status: dict[str, object],
    *,
    strength: float,
    regions: frozenset[str],
) -> dict[str, object]:
    """Compare one neutral SAM body with one live VaM skeleton."""

    strength = normalize_strength(strength)
    regions = normalize_regions(regions)
    target_measurements = target["measurements"]
    live_measurements = live["measurements"]
    assert isinstance(target_measurements, dict)
    assert isinstance(live_measurements, dict)

    rows: list[dict[str, object]] = []
    for metric in BODY_PROPORTION_METRICS:
        target_item = target_measurements[metric]
        live_item = live_measurements[metric]
        assert isinstance(target_item, dict)
        assert isinstance(live_item, dict)
        target_ratio = float(target_item["ratio"])
        current_ratio = float(live_item["ratio"])
        relative = target_ratio / current_ratio - 1.0
        label, region = _METRIC_PRESENTATION[metric]
        rows.append(
            {
                "id": metric,
                "label": label,
                "region": region,
                "enabled": region in regions,
                "targetRatio": target_ratio,
                "currentRatio": current_ratio,
                "deltaPercent": relative * 100.0,
                "confidence": min(
                    float(target_item["confidence"]),
                    float(live_item["confidence"]),
                ),
            }
        )

    available = _live_morphs(body_status.get("morphs"))
    changes: list[dict[str, object]] = []
    unavailable: list[dict[str, object]] = []
    for mapping in _MORPH_TARGETS:
        region = str(mapping["region"])
        if region not in regions:
            continue
        names = tuple(str(name) for name in mapping["names"])
        candidate = None
        ambiguous_name = ""
        for name in names:
            matches = [
                item
                for item in available
                if str(item["name"]).casefold() == name.casefold()
            ]
            if len(matches) > 1:
                ambiguous_name = name
                break
            if len(matches) == 1:
                candidate = matches[0]
                break
        if ambiguous_name:
            unavailable.append(
                {
                    "region": region,
                    "reason": (
                        f"Multiple verified {ambiguous_name} morphs are loaded; "
                        "VaM must expose an unambiguous built-in morph."
                    ),
                }
            )
            continue
        if candidate is None:
            unavailable.append(
                {
                    "region": region,
                    "reason": f"No verified {' / '.join(names)} morph is loaded.",
                }
            )
            continue
        target_ratio, target_confidence = _combined_ratio(
            target, mapping["metrics"]
        )
        current_ratio, live_confidence = _combined_ratio(
            live, mapping["metrics"]
        )
        confidence = min(target_confidence, live_confidence)
        relative = target_ratio / current_ratio - 1.0
        if confidence < 0.3:
            unavailable.append(
                {
                    "region": region,
                    "reason": "The source estimate is too uncertain for automatic fitting.",
                }
            )
            continue
        if abs(relative) < _MIN_RATIO_CHANGE:
            continue
        relative = max(-_MAX_RATIO_CHANGE, min(_MAX_RATIO_CHANGE, relative))
        response = float(mapping["fraction_per_value"])
        requested_delta = relative / response * strength
        requested_delta = max(
            -_MAX_VALUE_CHANGE,
            min(_MAX_VALUE_CHANGE, requested_delta),
        )
        current = float(candidate["value"])
        proposed = max(
            float(candidate["min"]),
            min(float(candidate["max"]), current + requested_delta),
        )
        if abs(proposed - current) < 1e-5:
            continue
        changes.append(
            {
                "key": candidate["key"],
                "name": candidate["name"],
                "region": region,
                "from": current,
                "value": proposed,
                "delta": proposed - current,
                "targetDeltaPercent": relative * 100.0,
                "confidence": confidence,
                "metrics": list(mapping["metrics"]),
            }
        )

    revision = body_status.get("revision")
    ready = (
        body_status.get("ready") is True
        and isinstance(revision, str)
        and _OPAQUE_TOKEN.fullmatch(revision) is not None
    )
    undo_available = body_status.get("undoAvailable") is True
    return {
        "schema": BODY_PROPORTION_SCHEMA,
        "ready": ready,
        "bodyRevision": revision if ready else None,
        "strength": strength,
        "regions": sorted(regions),
        "target": target,
        "current": live,
        "measurements": rows,
        "changes": changes[:8],
        "unavailable": unavailable,
        "canApply": bool(ready and changes and not undo_available),
        "undoAvailable": undo_available,
        "warning": (
            "This fits skeletal proportions only. Dynamic soft-body physics "
            "and face morphs are not changed. Body Scale stays untouched, "
            "but length morphs can change the Person's final height."
        ),
    }
