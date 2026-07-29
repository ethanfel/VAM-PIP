"""Validated, pose-neutral SAM 3D Body soft-shape signatures.

This module deliberately depends only on the Python standard library.  The
manager imports it to validate persisted worker output, while the native SAM
worker performs the NumPy mesh measurements in ``sam3d_shape_geometry``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from statistics import median
from typing import Iterable


BODY_SHAPE_SCHEMA = 1
BODY_SHAPE_SPACE = "mhr-neutral-bind"
BODY_SHAPE_CONFIDENCE_KIND = "heuristic-evidence-consistency"
BODY_SHAPE_METRICS = (
    "bustGirth",
    "bustWidth",
    "bustDepth",
    "underbustGirth",
    "underbustWidth",
    "underbustDepth",
    "breastGirthExcess",
    "breastDepthExcess",
    "breastProjection",
    "waistGirth",
    "waistWidth",
    "waistDepth",
    "seatGirth",
    "seatWidth",
    "seatDepth",
    "gluteProjection",
    "upperThighGirth",
    "upperThighWidth",
    "upperThighDepth",
)
BODY_SHAPE_REGIONS = (
    "breasts",
    "waist",
    "hips",
    "glutes",
    "thighs",
)
BODY_SHAPE_REGION_METRICS = {
    "breasts": (
        "bustGirth",
        "bustWidth",
        "bustDepth",
        "underbustGirth",
        "underbustWidth",
        "underbustDepth",
        "breastGirthExcess",
        "breastDepthExcess",
        "breastProjection",
    ),
    "waist": (
        "waistGirth",
        "waistWidth",
        "waistDepth",
    ),
    "hips": (
        "seatGirth",
        "seatWidth",
    ),
    "glutes": (
        "seatDepth",
        "gluteProjection",
    ),
    "thighs": (
        "upperThighGirth",
        "upperThighWidth",
        "upperThighDepth",
    ),
}
BODY_SHAPE_PLANES = (
    "bustTorsoFraction",
    "underbustTorsoFraction",
    "waistTorsoFraction",
    "seatTorsoFraction",
    "upperThighLegFraction",
)
_SIGNED_METRICS = frozenset(
    {
        "breastGirthExcess",
        "breastDepthExcess",
        "breastProjection",
        "gluteProjection",
    }
)
_BILATERAL_METRICS = frozenset(
    {
        "upperThighGirth",
        "upperThighWidth",
        "upperThighDepth",
    }
)
_OPAQUE_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VAM_SIMPLEJSON_NUMBER = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
)
_MAX_CONSENSUS_SIGNATURES = 8
_SIDECAR_KIND = "vampip-sam3d-body-shape-sidecar"
_VAM_FLOAT32_RELATIVE_TOLERANCE = 2e-6
_VAM_FLOAT32_ABSOLUTE_TOLERANCE = 2e-7


def _coerce_simplejson_number(value: object) -> object:
    """Return VaM SimpleJSON numeric strings as finite Python floats."""

    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 64
        or _VAM_SIMPLEJSON_NUMBER.fullmatch(value) is None
    ):
        return value
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return value
    return number if math.isfinite(number) else value


def _coerce_simplejson_int(value: object) -> object:
    return BODY_SHAPE_SCHEMA if value == str(BODY_SHAPE_SCHEMA) else value


def _vam_float32_matches(actual: float, expected: float) -> bool:
    return math.isclose(
        actual,
        expected,
        rel_tol=_VAM_FLOAT32_RELATIVE_TOLERANCE,
        abs_tol=_VAM_FLOAT32_ABSOLUTE_TOLERANCE,
    )


def _vam_finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _canonicalize_vam_float32_relations(
    document: dict[str, object],
) -> None:
    """Repair only redundant values lost to VaM's float32 text precision."""

    normalizer = document.get("normalizer")
    regions = document.get("regions")
    measurements = document.get("measurements")
    if (
        not isinstance(normalizer, dict)
        or not isinstance(regions, dict)
        or not isinstance(measurements, dict)
    ):
        return
    structural_length = _vam_finite_float(normalizer.get("meters"))
    if structural_length is None or structural_length == 0.0:
        return

    region_confidences: dict[str, float] = {}
    for region in BODY_SHAPE_REGIONS:
        status = regions.get(region)
        if not isinstance(status, dict):
            return
        geometry = _vam_finite_float(status.get("geometryConfidence"))
        evidence = _vam_finite_float(status.get("evidenceConfidence"))
        confidence = _vam_finite_float(status.get("confidence"))
        if geometry is None or evidence is None or confidence is None:
            return
        expected = min(geometry, evidence)
        if not _vam_float32_matches(confidence, expected):
            raise ValueError(f"body shape {region} confidence is invalid")
        status["confidence"] = expected
        region_confidences[region] = expected

    region_for_metric = {
        metric: region
        for region, metrics in BODY_SHAPE_REGION_METRICS.items()
        for metric in metrics
    }
    for metric in BODY_SHAPE_METRICS:
        measurement = measurements.get(metric)
        if not isinstance(measurement, dict):
            return
        meters = _vam_finite_float(measurement.get("meters"))
        ratio = _vam_finite_float(measurement.get("ratio"))
        confidence = _vam_finite_float(measurement.get("confidence"))
        if meters is None or ratio is None or confidence is None:
            return
        if metric in _BILATERAL_METRICS:
            left = _vam_finite_float(measurement.get("leftMeters"))
            right = _vam_finite_float(measurement.get("rightMeters"))
            if left is None or right is None:
                return
            expected_meters = (left + right) * 0.5
            if not _vam_float32_matches(meters, expected_meters):
                raise ValueError(f"body shape {metric} sides are invalid")
            measurement["meters"] = expected_meters
            meters = expected_meters

        expected_ratio = meters / structural_length
        if not _vam_float32_matches(ratio, expected_ratio):
            raise ValueError(f"body shape {metric} is invalid")
        measurement["ratio"] = expected_ratio

        expected_confidence = region_confidences[region_for_metric[metric]]
        if not _vam_float32_matches(confidence, expected_confidence):
            raise ValueError(f"body shape {metric} is invalid")
        measurement["confidence"] = expected_confidence

    overall = _vam_finite_float(document.get("overallConfidence"))
    if overall is None:
        return
    expected_overall = sum(region_confidences.values()) / len(region_confidences)
    if not _vam_float32_matches(overall, expected_overall):
        raise ValueError("body shape overallConfidence is invalid")
    document["overallConfidence"] = expected_overall


def normalize_vam_body_shape(value: object) -> dict[str, object]:
    """Canonicalize one body-shape signature emitted by VaM's SimpleJSON.

    VaM 1.22 serializes numbers in its JSON nodes as quoted scalar strings.
    Only the fixed numeric fields in the body-shape contract are converted;
    strict schema and range validation still runs before the value is trusted.
    """

    try:
        normalized = json.loads(
            json.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            )
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("body shape has an invalid schema") from exc
    if not isinstance(normalized, dict):
        raise ValueError("body shape has an invalid schema")

    normalized["schema"] = _coerce_simplejson_int(normalized.get("schema"))
    normalizer = normalized.get("normalizer")
    if isinstance(normalizer, dict):
        normalizer["meters"] = _coerce_simplejson_number(normalizer.get("meters"))

    measurements = normalized.get("measurements")
    if isinstance(measurements, dict):
        for metric in BODY_SHAPE_METRICS:
            measurement = measurements.get(metric)
            if not isinstance(measurement, dict):
                continue
            for key in (
                "meters",
                "ratio",
                "confidence",
                "leftMeters",
                "rightMeters",
            ):
                if key in measurement:
                    measurement[key] = _coerce_simplejson_number(measurement.get(key))

    regions = normalized.get("regions")
    if isinstance(regions, dict):
        for region in BODY_SHAPE_REGIONS:
            status = regions.get(region)
            if not isinstance(status, dict):
                continue
            for key in (
                "geometryConfidence",
                "evidenceConfidence",
                "confidence",
            ):
                status[key] = _coerce_simplejson_number(status.get(key))

    planes = normalized.get("planes")
    if isinstance(planes, dict):
        for key in BODY_SHAPE_PLANES:
            planes[key] = _coerce_simplejson_number(planes.get(key))
    normalized["overallConfidence"] = _coerce_simplejson_number(
        normalized.get("overallConfidence")
    )

    _canonicalize_vam_float32_relations(normalized)
    validate_body_shape(normalized)
    return normalized


def _finite_number(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _exact_dict(
    value: object,
    expected: Iterable[str],
    *,
    label: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{label} has an invalid schema")
    return value


def _measurement_confidence(
    regions: dict[str, object],
    metric: str,
) -> float:
    region = next(
        name for name, metrics in BODY_SHAPE_REGION_METRICS.items() if metric in metrics
    )
    value = regions[region]
    assert isinstance(value, dict)
    return float(value["confidence"])


def validate_body_shape(value: object) -> None:
    """Strictly validate one serialized neutral body-shape signature."""

    if not isinstance(value, dict):
        raise ValueError("body shape has an invalid schema")
    expected = {
        "schema",
        "space",
        "normalizer",
        "confidenceKind",
        "measurements",
        "regions",
        "planes",
        "overallConfidence",
    }
    if "consensus" in value:
        expected.add("consensus")
    document = _exact_dict(value, expected, label="body shape")
    if (
        document["schema"] != BODY_SHAPE_SCHEMA
        or document["space"] != BODY_SHAPE_SPACE
        or document["confidenceKind"] != BODY_SHAPE_CONFIDENCE_KIND
    ):
        raise ValueError("body shape identity is invalid")

    normalizer = _exact_dict(
        document["normalizer"],
        {"id", "meters"},
        label="body shape normalizer",
    )
    structural_length = _finite_number(
        normalizer["meters"],
        label="body shape structural length",
    )
    if normalizer["id"] != "structural-length" or not 0.25 <= structural_length <= 4.0:
        raise ValueError("body shape normalizer is invalid")

    regions = _exact_dict(
        document["regions"],
        BODY_SHAPE_REGIONS,
        label="body shape regions",
    )
    region_confidences: list[float] = []
    for region in BODY_SHAPE_REGIONS:
        status = _exact_dict(
            regions[region],
            {"geometryConfidence", "evidenceConfidence", "confidence"},
            label=f"body shape {region} region",
        )
        geometry = _finite_number(
            status["geometryConfidence"],
            label=f"body shape {region}.geometryConfidence",
        )
        evidence = _finite_number(
            status["evidenceConfidence"],
            label=f"body shape {region}.evidenceConfidence",
        )
        confidence = _finite_number(
            status["confidence"],
            label=f"body shape {region}.confidence",
        )
        if (
            not 0.0 <= geometry <= 1.0
            or not 0.0 <= evidence <= 1.0
            or not 0.0 <= confidence <= 1.0
            or abs(confidence - min(geometry, evidence)) > 2e-7
        ):
            raise ValueError(f"body shape {region} confidence is invalid")
        region_confidences.append(confidence)

    measurements = _exact_dict(
        document["measurements"],
        BODY_SHAPE_METRICS,
        label="body shape measurements",
    )
    for metric in BODY_SHAPE_METRICS:
        expected_measurement = {"meters", "ratio", "confidence"}
        if metric in _BILATERAL_METRICS:
            expected_measurement.update({"leftMeters", "rightMeters"})
        measurement = _exact_dict(
            measurements[metric],
            expected_measurement,
            label=f"body shape {metric}",
        )
        meters = _finite_number(
            measurement["meters"],
            label=f"body shape {metric}.meters",
        )
        ratio = _finite_number(
            measurement["ratio"],
            label=f"body shape {metric}.ratio",
        )
        confidence = _finite_number(
            measurement["confidence"],
            label=f"body shape {metric}.confidence",
        )
        if metric in _SIGNED_METRICS:
            value_valid = (
                -structural_length < meters < structural_length and -1.0 < ratio < 1.0
            )
        else:
            value_valid = 1e-6 < meters < structural_length * 4.0 and 0.0 < ratio < 4.0
        if (
            not value_valid
            or abs(ratio - meters / structural_length) > 2e-7
            or abs(confidence - _measurement_confidence(regions, metric)) > 2e-7
        ):
            raise ValueError(f"body shape {metric} is invalid")
        if metric in _BILATERAL_METRICS:
            left = _finite_number(
                measurement["leftMeters"],
                label=f"body shape {metric}.leftMeters",
            )
            right = _finite_number(
                measurement["rightMeters"],
                label=f"body shape {metric}.rightMeters",
            )
            if (
                not 1e-6 < left < structural_length * 4.0
                or not 1e-6 < right < structural_length * 4.0
                or abs(meters - (left + right) * 0.5) > 2e-7
            ):
                raise ValueError(f"body shape {metric} sides are invalid")

    planes = _exact_dict(
        document["planes"],
        BODY_SHAPE_PLANES,
        label="body shape planes",
    )
    plane_values = {
        name: _finite_number(
            planes[name],
            label=f"body shape planes.{name}",
        )
        for name in BODY_SHAPE_PLANES
    }
    if (
        not 0.58 <= plane_values["bustTorsoFraction"] <= 0.76
        or not 0.50 <= plane_values["underbustTorsoFraction"] <= 0.64
        or not 0.34 <= plane_values["waistTorsoFraction"] <= 0.58
        or not -0.08 <= plane_values["seatTorsoFraction"] <= 0.12
        or not 0.30 <= plane_values["upperThighLegFraction"] <= 0.40
    ):
        raise ValueError("body shape measurement planes are invalid")

    overall = _finite_number(
        document["overallConfidence"],
        label="body shape overallConfidence",
    )
    expected_overall = sum(region_confidences) / len(region_confidences)
    if not 0.0 <= overall <= 1.0 or abs(overall - expected_overall) > 2e-7:
        raise ValueError("body shape overallConfidence is invalid")

    if "consensus" in document:
        _validate_consensus(document["consensus"], len(BODY_SHAPE_REGIONS))


def _validate_index_list(
    value: object,
    *,
    source_count: int,
    label: str,
) -> list[int]:
    if (
        not isinstance(value, list)
        or any(
            isinstance(item, bool)
            or not isinstance(item, int)
            or not 0 <= item < source_count
            for item in value
        )
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _validate_consensus(value: object, expected_regions: int) -> None:
    report = _exact_dict(
        value,
        {
            "schema",
            "method",
            "confidenceSemantics",
            "sourceCount",
            "sources",
            "regions",
            "overallRelativeDisagreement",
            "maximumRelativeDisagreement",
            "rejectedRegionCount",
        },
        label="body shape consensus",
    )
    source_count = report["sourceCount"]
    if (
        report["schema"] != 1
        or report["method"]
        != "region-vector-median-gated-bounded-confidence-weighted-mean"
        or report["confidenceSemantics"]
        != "heuristic evidence and cross-source consistency; not probability"
        or isinstance(source_count, bool)
        or not isinstance(source_count, int)
        or not 2 <= source_count <= _MAX_CONSENSUS_SIGNATURES
    ):
        raise ValueError("body shape consensus identity is invalid")
    sources = report["sources"]
    if not isinstance(sources, list) or len(sources) != source_count:
        raise ValueError("body shape consensus sources are invalid")
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or source.get("index") != index:
            raise ValueError("body shape consensus source is invalid")
        if set(source) not in ({"index"}, {"index", "jobId"}):
            raise ValueError("body shape consensus source is invalid")
        if "jobId" in source and (
            not isinstance(source["jobId"], str)
            or _OPAQUE_TOKEN.fullmatch(source["jobId"]) is None
        ):
            raise ValueError("body shape consensus source job ID is invalid")

    regions = _exact_dict(
        report["regions"],
        BODY_SHAPE_REGIONS,
        label="body shape consensus regions",
    )
    disagreements: list[float] = []
    rejected_count = 0
    for region in BODY_SHAPE_REGIONS:
        item = _exact_dict(
            regions[region],
            {
                "usedSourceIndices",
                "rejectedSourceIndices",
                "relativeDisagreement",
            },
            label=f"body shape consensus {region}",
        )
        used = _validate_index_list(
            item["usedSourceIndices"],
            source_count=source_count,
            label=f"body shape consensus {region} used sources",
        )
        rejected = _validate_index_list(
            item["rejectedSourceIndices"],
            source_count=source_count,
            label=f"body shape consensus {region} rejected sources",
        )
        if len(used) < 2 or sorted(used + rejected) != list(range(source_count)):
            raise ValueError(f"body shape consensus {region} coverage is invalid")
        disagreement = _finite_number(
            item["relativeDisagreement"],
            label=f"body shape consensus {region} disagreement",
        )
        if not 0.0 <= disagreement <= 4.0:
            raise ValueError(f"body shape consensus {region} disagreement is invalid")
        disagreements.append(disagreement)
        rejected_count += len(rejected)

    overall = _finite_number(
        report["overallRelativeDisagreement"],
        label="body shape consensus overall disagreement",
    )
    maximum = _finite_number(
        report["maximumRelativeDisagreement"],
        label="body shape consensus maximum disagreement",
    )
    if (
        expected_regions != len(disagreements)
        or abs(overall - sum(disagreements) / len(disagreements)) > 2e-7
        or abs(maximum - max(disagreements)) > 2e-7
        or report["rejectedRegionCount"] != rejected_count
    ):
        raise ValueError("body shape consensus summary is invalid")


def _consensus_weight(confidence: float) -> float:
    return 0.25 + 0.75 * confidence


def _region_acceptance(
    signatures: list[dict[str, object]],
    region: str,
) -> tuple[list[int], list[int], float]:
    metrics = BODY_SHAPE_REGION_METRICS[region]
    values: dict[str, list[float]] = {}
    for metric in metrics:
        values[metric] = [
            float(signature["measurements"][metric]["ratio"])  # type: ignore[index]
            for signature in signatures
        ]
    centers = {metric: median(items) for metric, items in values.items()}
    distances: list[float] = []
    for index in range(len(signatures)):
        components = [
            abs(values[metric][index] - centers[metric])
            / max(abs(centers[metric]), 0.02)
            for metric in metrics
        ]
        distances.append(
            math.sqrt(
                sum(component * component for component in components) / len(components)
            )
        )

    accepted = list(range(len(signatures)))
    if len(signatures) >= 3:
        distance_center = median(distances)
        distance_mad = median(abs(distance - distance_center) for distance in distances)
        gate = distance_center + max(0.04, min(0.20, 4.4478 * distance_mad))
        accepted = [
            index for index, distance in enumerate(distances) if distance <= gate
        ]
        if len(accepted) < 2:
            accepted = sorted(
                range(len(signatures)),
                key=lambda index: (distances[index], index),
            )[:2]
    rejected = [index for index in range(len(signatures)) if index not in accepted]

    squared: list[float] = []
    for metric in metrics:
        selected = [values[metric][index] for index in accepted]
        center = sum(selected) / len(selected)
        scale = max(abs(center), 0.02)
        squared.extend(((value - center) / scale) ** 2 for value in selected)
    disagreement = math.sqrt(sum(squared) / len(squared)) if squared else 0.0
    return accepted, rejected, disagreement


def _rounded(value: float) -> float:
    return round(value, 8)


def consensus_body_shapes(
    signatures: Iterable[dict[str, object]],
    *,
    source_ids: Iterable[str] | None = None,
) -> dict[str, object]:
    """Combine 1-8 body-shape signatures with whole-region outlier gating."""

    if isinstance(signatures, dict):
        raise TypeError("signatures must be a list of body-shape signatures")
    values = list(signatures)
    if not 1 <= len(values) <= _MAX_CONSENSUS_SIGNATURES:
        raise ValueError("body-shape consensus requires 1 to 8 signatures")
    for signature in values:
        validate_body_shape(signature)
        if "consensus" in signature:
            raise ValueError("body-shape consensus inputs cannot be consensus results")

    normalized_source_ids: list[str] | None = None
    if source_ids is not None:
        if isinstance(source_ids, (str, bytes)):
            raise TypeError("source_ids must be a list of SAM3D job IDs")
        normalized_source_ids = list(source_ids)
        if (
            len(normalized_source_ids) != len(values)
            or len(set(normalized_source_ids)) != len(normalized_source_ids)
            or any(
                not isinstance(source_id, str)
                or _OPAQUE_TOKEN.fullmatch(source_id) is None
                for source_id in normalized_source_ids
            )
        ):
            raise ValueError("source_ids must be unique lowercase SAM3D job IDs")
    if len(values) == 1:
        return values[0]

    normalizers = [
        float(signature["normalizer"]["meters"])  # type: ignore[index]
        for signature in values
    ]
    consensus_normalizer = median(normalizers)
    acceptance: dict[str, tuple[list[int], list[int], float]] = {
        region: _region_acceptance(values, region) for region in BODY_SHAPE_REGIONS
    }

    regions: dict[str, dict[str, float]] = {}
    measurements: dict[str, dict[str, float]] = {}
    for region in BODY_SHAPE_REGIONS:
        accepted, _, disagreement = acceptance[region]
        source_statuses = [values[index]["regions"][region] for index in accepted]  # type: ignore[index]
        source_confidences = [
            float(status["confidence"])
            for status in source_statuses  # type: ignore[index]
        ]
        weights = [_consensus_weight(confidence) for confidence in source_confidences]
        weight_total = sum(weights)
        geometry = (
            sum(
                float(status["geometryConfidence"]) * weight  # type: ignore[index]
                for status, weight in zip(source_statuses, weights)
            )
            / weight_total
        )
        evidence = (
            sum(
                float(status["evidenceConfidence"]) * weight  # type: ignore[index]
                for status, weight in zip(source_statuses, weights)
            )
            / weight_total
        )
        penalty = (1.0 - min(0.5, disagreement * 2.0)) * (
            0.75 + 0.25 * len(accepted) / len(values)
        )
        geometry = max(0.0, min(1.0, geometry * penalty))
        evidence = max(0.0, min(1.0, evidence * penalty))
        confidence = min(geometry, evidence)
        regions[region] = {
            "geometryConfidence": _rounded(geometry),
            "evidenceConfidence": _rounded(evidence),
            "confidence": _rounded(confidence),
        }
        for metric in BODY_SHAPE_REGION_METRICS[region]:
            source_measurements = [
                values[index]["measurements"][metric]
                for index in accepted  # type: ignore[index]
            ]
            ratios = [
                float(measurement["ratio"])  # type: ignore[index]
                for measurement in source_measurements
            ]
            combined_ratio = (
                sum(ratio * weight for ratio, weight in zip(ratios, weights))
                / weight_total
            )
            item: dict[str, float] = {
                "meters": _rounded(combined_ratio * consensus_normalizer),
                "ratio": _rounded(combined_ratio),
                "confidence": _rounded(confidence),
            }
            if metric in _BILATERAL_METRICS:
                for side in ("leftMeters", "rightMeters"):
                    side_ratios = [
                        float(measurement[side])  # type: ignore[index]
                        / float(values[index]["normalizer"]["meters"])  # type: ignore[index]
                        for measurement, index in zip(source_measurements, accepted)
                    ]
                    item[side] = _rounded(
                        sum(
                            ratio * weight
                            for ratio, weight in zip(side_ratios, weights)
                        )
                        / weight_total
                        * consensus_normalizer
                    )
                item["meters"] = _rounded(
                    (item["leftMeters"] + item["rightMeters"]) * 0.5
                )
                item["ratio"] = _rounded(item["meters"] / consensus_normalizer)
            measurements[metric] = item

    plane_region = {
        "bustTorsoFraction": "breasts",
        "underbustTorsoFraction": "breasts",
        "waistTorsoFraction": "waist",
        "seatTorsoFraction": "hips",
        "upperThighLegFraction": "thighs",
    }
    planes: dict[str, float] = {}
    for plane, region in plane_region.items():
        accepted = acceptance[region][0]
        planes[plane] = _rounded(
            median(
                float(values[index]["planes"][plane])  # type: ignore[index]
                for index in accepted
            )
        )

    result: dict[str, object] = {
        "schema": BODY_SHAPE_SCHEMA,
        "space": BODY_SHAPE_SPACE,
        "normalizer": {
            "id": "structural-length",
            "meters": _rounded(consensus_normalizer),
        },
        "confidenceKind": BODY_SHAPE_CONFIDENCE_KIND,
        "measurements": measurements,
        "regions": regions,
        "planes": planes,
        "overallConfidence": _rounded(
            sum(status["confidence"] for status in regions.values()) / len(regions)
        ),
    }
    sources: list[dict[str, object]] = []
    for index in range(len(values)):
        source: dict[str, object] = {"index": index}
        if normalized_source_ids is not None:
            source["jobId"] = normalized_source_ids[index]
        sources.append(source)
    disagreements = [acceptance[region][2] for region in BODY_SHAPE_REGIONS]
    result["consensus"] = {
        "schema": 1,
        "method": "region-vector-median-gated-bounded-confidence-weighted-mean",
        "confidenceSemantics": (
            "heuristic evidence and cross-source consistency; not probability"
        ),
        "sourceCount": len(values),
        "sources": sources,
        "regions": {
            region: {
                "usedSourceIndices": acceptance[region][0],
                "rejectedSourceIndices": acceptance[region][1],
                "relativeDisagreement": _rounded(acceptance[region][2]),
            }
            for region in BODY_SHAPE_REGIONS
        },
        "overallRelativeDisagreement": _rounded(
            sum(disagreements) / len(disagreements)
        ),
        "maximumRelativeDisagreement": _rounded(max(disagreements)),
        "rejectedRegionCount": sum(
            len(acceptance[region][1]) for region in BODY_SHAPE_REGIONS
        ),
    }
    validate_body_shape(result)
    return result


def body_shape_sidecar_revision(document: dict[str, object]) -> str:
    """Return the content revision for an unsigned shape sidecar."""

    unsigned = {key: value for key, value in document.items() if key != "revision"}
    return hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()[:32]


def validate_body_shape_sidecar(value: object) -> None:
    """Validate a shape-only worker result and its source-binding revision."""

    document = _exact_dict(
        value,
        {"schema", "kind", "source", "bodyShape", "revision"},
        label="body shape sidecar",
    )
    if document["schema"] != 1 or document["kind"] != _SIDECAR_KIND:
        raise ValueError("body shape sidecar identity is invalid")
    source = _exact_dict(
        document["source"],
        {
            "arraysSha256",
            "arraysBytes",
            "personIndex",
            "mhrSha256",
            "identityBasisSha256",
        },
        label="body shape sidecar source",
    )
    if (
        any(
            not isinstance(source[name], str) or _SHA256.fullmatch(source[name]) is None
            for name in (
                "arraysSha256",
                "mhrSha256",
                "identityBasisSha256",
            )
        )
        or isinstance(source["arraysBytes"], bool)
        or not isinstance(source["arraysBytes"], int)
        or not 1 <= source["arraysBytes"] <= 512 * 1024 * 1024
        or isinstance(source["personIndex"], bool)
        or not isinstance(source["personIndex"], int)
        or not 0 <= source["personIndex"] <= 15
    ):
        raise ValueError("body shape sidecar source is invalid")
    validate_body_shape(document["bodyShape"])
    revision = document["revision"]
    if (
        not isinstance(revision, str)
        or _OPAQUE_TOKEN.fullmatch(revision) is None
        or revision != body_shape_sidecar_revision(document)
    ):
        raise ValueError("body shape sidecar revision is invalid")


__all__ = [
    "BODY_SHAPE_METRICS",
    "BODY_SHAPE_REGIONS",
    "BODY_SHAPE_REGION_METRICS",
    "body_shape_sidecar_revision",
    "consensus_body_shapes",
    "normalize_vam_body_shape",
    "validate_body_shape",
    "validate_body_shape_sidecar",
]
