"""Bounded body-shape fitting from neutral mesh signatures.

The bridge publishes a read-only local response for each allowlisted shape
morph.  This module solves those responses together so, for example, a hip
morph's small effect on the seat depth is not applied twice by the glute fit.
It deliberately knows nothing about face morphs or soft-body physics.
"""

from __future__ import annotations

import math
import re

from vampip.sam3d_body_shape import (
    BODY_SHAPE_METRICS,
    BODY_SHAPE_REGIONS,
    validate_body_shape,
)


BODY_SHAPE_SCHEMA = 1
MANUAL_BODY_SHAPE_SCHEMA = 1
_OPAQUE_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_MAX_VALUE_CHANGE = 0.25
_MAX_RELATIVE_TARGET = 0.15
_MIN_RELATIVE_TARGET = 0.0125
_MIN_CONFIDENCE = 0.30
_MAX_LIVE_MORPHS = 64
_MANUAL_SHAPE_VALUE_PRECISION = 6

# ChestSeparateBreasts' positive direction increases separation.  Keeping the
# direction named and server-owned prevents a WebUI client from choosing an
# arbitrary morph or reversing its semantics.
_BREAST_SPACING_DIRECTION = 1.0

_MANUAL_SHAPE_TARGETS = {
    "breast_size": ("breasts", "Breasts Size", 1.0),
    "breast_spacing": (
        "breasts",
        "ChestSeparateBreasts",
        _BREAST_SPACING_DIRECTION,
    ),
    "waist_width": ("waist", "Waist Width", 1.0),
    "hip_width": ("hips", "Hip Size", 1.0),
    "glute_projection": ("glutes", "Glutes Size", 1.0),
    "thigh_size": ("thighs", "Thighs Size", 1.0),
}

_MORPH_TARGETS = (
    ("breasts", "Breasts Size"),
    ("waist", "Waist Width"),
    ("hips", "Hip Size"),
    ("glutes", "Glutes Size"),
    ("thighs", "Thighs Size"),
)

_METRIC_PRESENTATION = {
    "bustGirth": ("Bust girth", "breasts"),
    "bustWidth": ("Bust width", "breasts"),
    "bustDepth": ("Bust depth", "breasts"),
    "underbustGirth": ("Underbust girth", "breasts"),
    "underbustWidth": ("Underbust width", "breasts"),
    "underbustDepth": ("Underbust depth", "breasts"),
    "breastGirthExcess": ("Breast fullness", "breasts"),
    "breastDepthExcess": ("Breast depth excess", "breasts"),
    "breastProjection": ("Breast projection", "breasts"),
    "waistGirth": ("Waist girth", "waist"),
    "waistWidth": ("Waist width", "waist"),
    "waistDepth": ("Waist depth", "waist"),
    "seatGirth": ("Seat girth", "hips"),
    "seatWidth": ("Hip width", "hips"),
    "seatDepth": ("Seat depth", "glutes"),
    "gluteProjection": ("Glute projection", "glutes"),
    "upperThighGirth": ("Upper-thigh girth", "thighs"),
    "upperThighWidth": ("Upper-thigh width", "thighs"),
    "upperThighDepth": ("Upper-thigh depth", "thighs"),
}

# Fit against compact, complementary metric vectors.  The UI can still show
# every raw section measurement in the signature.
_FIT_METRICS = {
    "breasts": ("breastGirthExcess", "breastProjection"),
    "waist": ("waistGirth", "waistWidth", "waistDepth"),
    "hips": ("seatWidth",),
    "glutes": ("gluteProjection", "seatDepth"),
    "thighs": (
        "upperThighGirth",
        "upperThighWidth",
        "upperThighDepth",
    ),
}


def _finite_number(
    value: object,
    *,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    if minimum is not None and result < minimum:
        raise ValueError(f"{label} is below its supported range")
    if maximum is not None and result > maximum:
        raise ValueError(f"{label} exceeds its supported range")
    return result


def normalize_shape_strength(value: object) -> float:
    return _finite_number(
        value,
        label="shape_strength",
        minimum=0.0,
        maximum=1.0,
    )


def normalize_shape_regions(value: object) -> frozenset[str]:
    if value is None:
        return frozenset()
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise TypeError("shape_regions must be a list")
    result: set[str] = set()
    for item in value:
        if not isinstance(item, str) or item not in BODY_SHAPE_REGIONS:
            raise ValueError("shape_regions contains an unsupported body region")
        result.add(item)
    return frozenset(result)


def normalize_manual_shape(value: object) -> dict[str, object]:
    """Return one canonical, bounded semantic manual-shape request.

    The browser may select only semantic controls.  Morph identifiers, names,
    absolute values, and revision tokens are deliberately absent from this
    contract and are resolved again from the live bridge catalog.
    """

    if value is None:
        return {"schema": MANUAL_BODY_SHAPE_SCHEMA, "offsets": {}}
    if not isinstance(value, dict) or set(value) != {"schema", "offsets"}:
        raise ValueError("manual_shape must contain only schema and offsets")
    schema = value.get("schema")
    if (
        isinstance(schema, bool)
        or not isinstance(schema, int)
        or schema != MANUAL_BODY_SHAPE_SCHEMA
    ):
        raise ValueError("manual_shape schema is unsupported")
    raw_offsets = value.get("offsets")
    if not isinstance(raw_offsets, dict):
        raise ValueError("manual_shape offsets must be an object")
    unexpected = sorted(set(raw_offsets) - set(_MANUAL_SHAPE_TARGETS))
    if unexpected:
        raise ValueError(
            "manual_shape contains unsupported offset(s): "
            + ", ".join(unexpected)
        )
    offsets: dict[str, float] = {}
    for control in _MANUAL_SHAPE_TARGETS:
        if control not in raw_offsets:
            continue
        offset = _finite_number(
            raw_offsets[control],
            label=f"manual_shape offsets.{control}",
            minimum=-1.0,
            maximum=1.0,
        )
        offset = round(offset, _MANUAL_SHAPE_VALUE_PRECISION)
        if offset != 0.0:
            offsets[control] = offset
    return {"schema": MANUAL_BODY_SHAPE_SCHEMA, "offsets": offsets}


def manual_shape_regions(value: object) -> frozenset[str]:
    normalized = normalize_manual_shape(value)
    offsets = normalized["offsets"]
    assert isinstance(offsets, dict)
    return frozenset(
        _MANUAL_SHAPE_TARGETS[control][0] for control in offsets
    )


def live_body_shape(value: object) -> dict[str, object]:
    """Validate and return the bridge's neutral-mesh shape signature."""

    if not isinstance(value, dict):
        raise ValueError("VaM body-shape measurements are unavailable")
    validate_body_shape(value)
    return value


def _measurement(
    signature: dict[str, object],
    metric: str,
) -> tuple[float, float]:
    raw = signature["measurements"]
    assert isinstance(raw, dict)
    item = raw[metric]
    assert isinstance(item, dict)
    return float(item["ratio"]), float(item["confidence"])


def _live_shape_morphs(
    value: object,
    *,
    require_responses: bool = True,
) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in value[:_MAX_LIVE_MORPHS]:
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
            or raw.get("builtIn") is not True
            or raw.get("fitKind") != "shape"
        ):
            continue
        try:
            current = _finite_number(
                raw.get("value"),
                label="shape morph value",
                minimum=-1.0,
                maximum=1.0,
            )
            minimum = _finite_number(
                raw.get("min"),
                label="shape morph minimum",
                minimum=-1.0,
                maximum=1.0,
            )
            maximum = _finite_number(
                raw.get("max"),
                label="shape morph maximum",
                minimum=-1.0,
                maximum=1.0,
            )
        except ValueError:
            continue
        if minimum > maximum or not minimum <= current <= maximum:
            continue
        responses: dict[str, float] = {}
        raw_responses = raw.get("shapeResponses")
        if raw_responses is not None and not isinstance(raw_responses, dict):
            continue
        if isinstance(raw_responses, dict):
            try:
                for metric, response in raw_responses.items():
                    if metric not in BODY_SHAPE_METRICS:
                        continue
                    responses[metric] = _finite_number(
                        response,
                        label=f"{name} {metric} response",
                        minimum=-10.0,
                        maximum=10.0,
                    )
            except ValueError:
                continue
        if require_responses and not responses:
            continue
        seen.add(key)
        result.append(
            {
                "key": key,
                "name": name,
                "region": str(raw.get("shapeRegion") or "")[:128],
                "value": current,
                "min": minimum,
                "max": maximum,
                "responses": responses,
            }
        )
    return result


def _apply_manual_shape_offsets(
    automatic_changes: list[dict[str, object]],
    body_status: dict[str, object],
    manual_shape: dict[str, object],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """Merge semantic corrections into server-derived automatic proposals."""

    offsets = manual_shape["offsets"]
    assert isinstance(offsets, dict)
    if not offsets:
        return automatic_changes, [], []

    available = _live_shape_morphs(
        body_status.get("morphs"),
        require_responses=False,
    )
    changes = [dict(change) for change in automatic_changes]
    change_positions = {
        str(change.get("key")): index
        for index, change in enumerate(changes)
        if isinstance(change.get("key"), str)
    }
    manual_changes: list[dict[str, object]] = []
    unavailable: list[dict[str, object]] = []

    for control, semantic_offset in offsets.items():
        region, name, direction = _MANUAL_SHAPE_TARGETS[control]
        candidate, reason = _candidate_for_name(available, name, region)
        if candidate is None:
            unavailable.append(
                {
                    "region": region,
                    "control": control,
                    "reason": reason or "",
                }
            )
            continue

        key = str(candidate["key"])
        current = float(candidate["value"])
        position = change_positions.get(key)
        automatic_value = (
            float(changes[position]["value"])
            if position is not None
            else current
        )
        requested_offset = (
            float(semantic_offset) * _MAX_VALUE_CHANGE * float(direction)
        )
        lower = max(float(candidate["min"]), current - _MAX_VALUE_CHANGE)
        upper = min(float(candidate["max"]), current + _MAX_VALUE_CHANGE)
        proposed = max(lower, min(upper, automatic_value + requested_offset))
        applied_offset = proposed - automatic_value
        limited = not math.isclose(
            applied_offset,
            requested_offset,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        manual_changes.append(
            {
                "control": control,
                "region": region,
                "name": name,
                "semanticOffset": float(semantic_offset),
                "requestedOffset": requested_offset,
                "appliedOffset": applied_offset,
                "limited": limited,
            }
        )

        if abs(proposed - current) < 1e-5:
            if position is not None:
                changes.pop(position)
                change_positions = {
                    str(change.get("key")): index
                    for index, change in enumerate(changes)
                    if isinstance(change.get("key"), str)
                }
            continue

        if position is None:
            changes.append(
                {
                    "key": key,
                    "name": name,
                    "region": region,
                    "fitKind": "shape",
                    "from": current,
                    "value": proposed,
                    "delta": proposed - current,
                    "metrics": [],
                    "manualControl": control,
                    "automaticValue": current,
                    "manualOffset": applied_offset,
                }
            )
            change_positions[key] = len(changes) - 1
            continue

        change = changes[position]
        change["value"] = proposed
        change["delta"] = proposed - current
        change["manualControl"] = control
        change["automaticValue"] = automatic_value
        change["manualOffset"] = applied_offset

    return changes, manual_changes, unavailable


def _solve_linear(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve one small dense system with partial-pivot Gauss-Jordan."""

    size = len(vector)
    augmented = [
        [float(item) for item in matrix[row]] + [float(vector[row])]
        for row in range(size)
    ]
    for column in range(size):
        pivot = max(
            range(column, size),
            key=lambda row: abs(augmented[row][column]),
        )
        if abs(augmented[pivot][column]) <= 1e-10:
            raise ValueError("body-shape response matrix is singular")
        augmented[column], augmented[pivot] = (
            augmented[pivot],
            augmented[column],
        )
        divisor = augmented[column][column]
        augmented[column] = [item / divisor for item in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if abs(factor) <= 1e-15:
                continue
            augmented[row] = [
                left - factor * right
                for left, right in zip(augmented[row], augmented[column])
            ]
    return [augmented[row][-1] for row in range(size)]


def _least_squares(
    rows: list[list[float]],
    targets: list[float],
    weights: list[float],
) -> list[float]:
    if not rows or not rows[0]:
        return []
    columns = len(rows[0])
    # A light ridge keeps weakly coupled or nearly redundant shape controls
    # stable without overwhelming useful local response measurements.
    ridge = 1e-6
    normal = [[0.0 for _ in range(columns)] for _ in range(columns)]
    rhs = [0.0 for _ in range(columns)]
    for row, target, weight in zip(rows, targets, weights):
        for left in range(columns):
            rhs[left] += weight * row[left] * target
            for right in range(columns):
                normal[left][right] += weight * row[left] * row[right]
    for index in range(columns):
        normal[index][index] += ridge
    return _solve_linear(normal, rhs)


def _candidate_for_name(
    available: list[dict[str, object]],
    name: str,
    region: str,
) -> tuple[dict[str, object] | None, str | None]:
    matches = [
        item
        for item in available
        if (
            str(item["name"]).casefold() == name.casefold() and item["region"] == region
        )
    ]
    if len(matches) > 1:
        return None, (
            f"Multiple verified {name} morphs are loaded; "
            "VaM must expose one unambiguous built-in morph."
        )
    if not matches:
        return None, f"The verified built-in {name} morph is not loaded."
    return matches[0], None


def build_body_shape_analysis(
    target: dict[str, object],
    live: dict[str, object],
    body_status: dict[str, object],
    *,
    strength: object,
    regions: object,
    manual_shape: object = None,
) -> dict[str, object]:
    """Compare target/live neutral meshes and propose one bounded joint fit."""

    validate_body_shape(target)
    validate_body_shape(live)
    strength_value = normalize_shape_strength(strength)
    region_values = normalize_shape_regions(regions)
    manual_shape_value = normalize_manual_shape(manual_shape)

    rows: list[dict[str, object]] = []
    for metric in BODY_SHAPE_METRICS:
        target_ratio, target_confidence = _measurement(target, metric)
        current_ratio, live_confidence = _measurement(live, metric)
        label, region = _METRIC_PRESENTATION[metric]
        rows.append(
            {
                "id": metric,
                "label": label,
                "region": region,
                "enabled": region in region_values,
                "targetRatio": target_ratio,
                "currentRatio": current_ratio,
                "deltaPercent": (
                    (target_ratio / current_ratio - 1.0) * 100.0
                    if abs(current_ratio) > 1e-9
                    else 0.0
                ),
                "confidence": min(target_confidence, live_confidence),
            }
        )

    available = _live_shape_morphs(body_status.get("morphs"))
    candidates: list[tuple[str, dict[str, object]]] = []
    unavailable: list[dict[str, object]] = []
    for region, name in _MORPH_TARGETS:
        if region not in region_values:
            continue
        candidate, reason = _candidate_for_name(available, name, region)
        if candidate is None:
            unavailable.append({"region": region, "reason": reason or ""})
            continue
        candidates.append((region, candidate))

    fit_rows: list[list[float]] = []
    fit_targets: list[float] = []
    fit_weights: list[float] = []
    used_metrics: set[str] = set()
    metric_confidences: dict[str, float] = {}
    has_meaningful_target = False
    for region in region_values:
        for metric in _FIT_METRICS[region]:
            target_ratio, target_confidence = _measurement(target, metric)
            current_ratio, live_confidence = _measurement(live, metric)
            confidence = min(target_confidence, live_confidence)
            metric_confidences[metric] = confidence
            if confidence < _MIN_CONFIDENCE:
                continue
            scale = max(abs(current_ratio), 0.01)
            relative = (target_ratio - current_ratio) / scale
            if abs(relative) >= _MIN_RELATIVE_TARGET:
                has_meaningful_target = True
            relative = max(
                -_MAX_RELATIVE_TARGET,
                min(_MAX_RELATIVE_TARGET, relative),
            )
            response_row: list[float] = []
            for _, candidate in candidates:
                responses = candidate["responses"]
                assert isinstance(responses, dict)
                response_row.append(float(responses.get(metric, 0.0)) / scale)
            if not any(abs(item) > 1e-7 for item in response_row):
                continue
            fit_rows.append(response_row)
            fit_targets.append(relative * strength_value)
            fit_weights.append(confidence * confidence)
            used_metrics.add(metric)

    solved: list[float] = []
    if has_meaningful_target and fit_rows and candidates:
        try:
            solved = _least_squares(fit_rows, fit_targets, fit_weights)
        except ValueError:
            unavailable.append(
                {
                    "region": "shape",
                    "reason": (
                        "The loaded shape morphs do not provide an independent "
                        "response for this body."
                    ),
                }
            )

    changes: list[dict[str, object]] = []
    for (region, candidate), delta in zip(candidates, solved):
        delta = max(-_MAX_VALUE_CHANGE, min(_MAX_VALUE_CHANGE, delta))
        current = float(candidate["value"])
        proposed = max(
            float(candidate["min"]),
            min(float(candidate["max"]), current + delta),
        )
        if abs(proposed - current) < 1e-5:
            continue
        metrics = [metric for metric in _FIT_METRICS[region] if metric in used_metrics]
        confidence = (
            min(metric_confidences[metric] for metric in metrics) if metrics else 0.0
        )
        changes.append(
            {
                "key": candidate["key"],
                "name": candidate["name"],
                "region": region,
                "fitKind": "shape",
                "from": current,
                "value": proposed,
                "delta": proposed - current,
                "confidence": confidence,
                "metrics": metrics,
            }
        )

    for region in region_values:
        metrics = _FIT_METRICS[region]
        if all(
            metric_confidences.get(metric, 0.0) < _MIN_CONFIDENCE for metric in metrics
        ):
            unavailable.append(
                {
                    "region": region,
                    "reason": (
                        "The references do not provide enough view evidence "
                        "for an automatic shape change."
                    ),
                }
            )

    automatic_changes = changes
    changes, manual_changes, manual_unavailable = _apply_manual_shape_offsets(
        automatic_changes,
        body_status,
        manual_shape_value,
    )
    unavailable.extend(manual_unavailable)

    result: dict[str, object] = {
        "schema": BODY_SHAPE_SCHEMA,
        "strength": strength_value,
        "regions": sorted(region_values),
        "target": target,
        "current": live,
        "measurements": rows,
        "changes": changes,
        "unavailable": unavailable,
        "confidence": target.get("overallConfidence"),
        "warning": (
            "Body Shape changes geometry only. Face morphs and breast/glute "
            "physics settings are excluded."
        ),
    }
    offsets = manual_shape_value["offsets"]
    assert isinstance(offsets, dict)
    if offsets:
        result.update(
            {
                "manual_shape": manual_shape_value,
                "manual_shape_regions": sorted(
                    manual_shape_regions(manual_shape_value)
                ),
                "automatic_changes": automatic_changes,
                "manual_changes": manual_changes,
            }
        )
    return result
