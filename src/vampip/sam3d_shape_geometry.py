"""Worker-side neutral MHR mesh measurements for body-shape fitting."""

from __future__ import annotations

import math
from typing import Any

try:
    from .sam3d_body_shape import (
        BODY_SHAPE_CONFIDENCE_KIND,
        BODY_SHAPE_METRICS,
        BODY_SHAPE_REGION_METRICS,
        BODY_SHAPE_SCHEMA,
        BODY_SHAPE_SPACE,
        validate_body_shape,
    )
except ImportError:  # Standalone native worker execution.
    from sam3d_body_shape import (  # type: ignore[no-redef]
        BODY_SHAPE_CONFIDENCE_KIND,
        BODY_SHAPE_METRICS,
        BODY_SHAPE_REGION_METRICS,
        BODY_SHAPE_SCHEMA,
        BODY_SHAPE_SPACE,
        validate_body_shape,
    )


_LEFT_SHOULDER = 5
_RIGHT_SHOULDER = 6
_LEFT_HIP = 9
_RIGHT_HIP = 10
_LEFT_KNEE = 11
_RIGHT_KNEE = 12
_LEFT_ANKLE = 13
_RIGHT_ANKLE = 14
_NOSE = 0
_BILATERAL_METRICS = frozenset(
    {"upperThighGirth", "upperThighWidth", "upperThighDepth"}
)


def _rounded(value: float) -> float:
    return round(float(value), 8)


def _norm(np: Any, value: Any, *, label: str) -> float:
    result = float(np.linalg.norm(value))
    if not math.isfinite(result) or result <= 1e-8:
        raise ValueError(f"{label} is invalid")
    return result


def _distance(np: Any, first: Any, second: Any) -> float:
    return float(np.linalg.norm(first - second))


def _anatomical_frame(np: Any, keypoints: Any) -> dict[str, Any]:
    left_shoulder = keypoints[_LEFT_SHOULDER]
    right_shoulder = keypoints[_RIGHT_SHOULDER]
    left_hip = keypoints[_LEFT_HIP]
    right_hip = keypoints[_RIGHT_HIP]
    shoulder_midpoint = (left_shoulder + right_shoulder) * 0.5
    hip_midpoint = (left_hip + right_hip) * 0.5

    lateral = left_shoulder - right_shoulder
    lateral /= _norm(np, lateral, label="neutral MHR lateral axis")
    up = shoulder_midpoint - hip_midpoint
    up -= lateral * float(np.dot(up, lateral))
    torso_length = _norm(np, up, label="neutral MHR torso axis")
    up /= torso_length
    front = np.cross(lateral, up)
    front /= _norm(np, front, label="neutral MHR front axis")
    if float(np.dot(keypoints[_NOSE] - shoulder_midpoint, front)) < 0.0:
        front *= -1.0

    thigh = (
        _distance(np, left_hip, keypoints[_LEFT_KNEE])
        + _distance(np, right_hip, keypoints[_RIGHT_KNEE])
    ) * 0.5
    shin = (
        _distance(np, keypoints[_LEFT_KNEE], keypoints[_LEFT_ANKLE])
        + _distance(np, keypoints[_RIGHT_KNEE], keypoints[_RIGHT_ANKLE])
    ) * 0.5
    structural_length = torso_length + thigh + shin
    if not 0.25 <= structural_length <= 4.0:
        raise ValueError("neutral MHR structural length is outside the safe range")
    knee_midpoint = (keypoints[_LEFT_KNEE] + keypoints[_RIGHT_KNEE]) * 0.5
    hip_to_knee = float(np.dot(hip_midpoint - knee_midpoint, up))
    if not 0.05 <= hip_to_knee < structural_length:
        raise ValueError("neutral MHR hip-to-knee projection is invalid")
    shoulder_span = _distance(np, left_shoulder, right_shoulder)
    return {
        "origin": hip_midpoint,
        "lateral": lateral,
        "up": up,
        "front": front,
        "torsoLength": torso_length,
        "hipToKnee": hip_to_knee,
        "structuralLength": structural_length,
        "shoulderSpan": shoulder_span,
    }


def _mesh_edges(np: Any, faces: Any) -> tuple[Any, Any]:
    edge_rows = np.concatenate(
        (
            faces[:, (0, 1)],
            faces[:, (1, 2)],
            faces[:, (2, 0)],
        ),
        axis=0,
    )
    edge_rows = np.sort(edge_rows, axis=1)
    edges, inverse = np.unique(edge_rows, axis=0, return_inverse=True)
    count = len(faces)
    face_edges = np.stack(
        (
            inverse[:count],
            inverse[count : count * 2],
            inverse[count * 2 :],
        ),
        axis=1,
    )
    return edges, face_edges


def _section_contours(
    np: Any,
    vertices: Any,
    edges: Any,
    face_edges: Any,
    *,
    frame: dict[str, Any],
    offset: float,
) -> list[dict[str, float | bool]]:
    origin = frame["origin"]
    up = frame["up"]
    lateral = frame["lateral"]
    front = frame["front"]
    structural_length = float(frame["structuralLength"])
    # Moving off exact mesh vertices avoids ambiguous high-degree intersections
    # while remaining far below the serialized measurement precision.
    plane_offset = offset + structural_length * 1.0e-7 * 0.61803398875
    signed = (vertices - origin) @ up - plane_offset
    first = signed[edges[:, 0]]
    second = signed[edges[:, 1]]
    crosses = (first > 0.0) != (second > 0.0)
    fractions = np.zeros(len(edges), dtype=np.float64)
    fractions[crosses] = first[crosses] / (first[crosses] - second[crosses])
    points = np.zeros((len(edges), 3), dtype=np.float64)
    points[crosses] = vertices[edges[crosses, 0]] + fractions[crosses, None] * (
        vertices[edges[crosses, 1]] - vertices[edges[crosses, 0]]
    )

    crossed_face_edges = crosses[face_edges]
    valid_faces = crossed_face_edges.sum(axis=1) == 2
    segments: list[tuple[int, int]] = []
    for edge_ids, edge_mask in zip(
        face_edges[valid_faces],
        crossed_face_edges[valid_faces],
    ):
        selected = edge_ids[edge_mask]
        segments.append((int(selected[0]), int(selected[1])))
    if not segments:
        return []

    adjacency: dict[int, list[int]] = {}
    for first_id, second_id in segments:
        adjacency.setdefault(first_id, []).append(second_id)
        adjacency.setdefault(second_id, []).append(first_id)

    components: list[list[int]] = []
    seen: set[int] = set()
    for start in adjacency:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        component: list[int] = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(component)

    component_by_node: dict[int, int] = {}
    for component_index, component in enumerate(components):
        for node in component:
            component_by_node[node] = component_index
    perimeters = [0.0 for _ in components]
    for first_id, second_id in segments:
        component_index = component_by_node[first_id]
        if component_by_node[second_id] == component_index:
            perimeters[component_index] += float(
                np.linalg.norm(points[first_id] - points[second_id])
            )

    contours: list[dict[str, float | bool]] = []
    for component_index, component in enumerate(components):
        local = points[component] - origin
        lateral_values = local @ lateral
        front_values = local @ front
        closed = all(len(adjacency[node]) == 2 for node in component)
        contours.append(
            {
                "center": float(np.mean(lateral_values)),
                "minimumLateral": float(np.min(lateral_values)),
                "maximumLateral": float(np.max(lateral_values)),
                "width": float(np.ptp(lateral_values)),
                "depth": float(np.ptp(front_values)),
                "front": float(np.max(front_values)),
                "back": float(np.min(front_values)),
                "girth": perimeters[component_index],
                "closed": closed,
            }
        )
    return contours


def _torso_contour(
    contours: list[dict[str, float | bool]],
    *,
    frame: dict[str, Any],
) -> dict[str, float | bool]:
    structural_length = float(frame["structuralLength"])
    maximum_width = max(
        float(frame["shoulderSpan"]) * 1.65,
        structural_length * 0.28,
    )
    candidates = [
        contour
        for contour in contours
        if contour["closed"] is True
        and float(contour["minimumLateral"]) <= 0.0
        and float(contour["maximumLateral"]) >= 0.0
        and structural_length * 0.04 < float(contour["width"]) < maximum_width
        and structural_length * 0.03
        < float(contour["depth"])
        < structural_length * 0.40
        and structural_length * 0.10 < float(contour["girth"]) < structural_length * 2.0
    ]
    if not candidates:
        raise ValueError("neutral MHR torso section is unavailable")
    return min(candidates, key=lambda contour: abs(float(contour["center"])))


def _torso_section(
    np: Any,
    vertices: Any,
    edges: Any,
    face_edges: Any,
    frame: dict[str, Any],
    fraction: float,
) -> dict[str, float | bool]:
    return _torso_contour(
        _section_contours(
            np,
            vertices,
            edges,
            face_edges,
            frame=frame,
            offset=fraction * float(frame["torsoLength"]),
        ),
        frame=frame,
    )


def _scan_torso(
    np: Any,
    vertices: Any,
    edges: Any,
    face_edges: Any,
    frame: dict[str, Any],
    *,
    first: float,
    last: float,
    selector: Any,
) -> tuple[float, dict[str, float | bool]]:
    count = int(round((last - first) / 0.01))
    values: list[tuple[float, dict[str, float | bool]]] = []
    for index in range(count + 1):
        fraction = round(first + index * 0.01, 8)
        values.append(
            (
                fraction,
                _torso_section(
                    np,
                    vertices,
                    edges,
                    face_edges,
                    frame,
                    fraction,
                ),
            )
        )
    return selector(values)


def _thigh_contours(
    np: Any,
    vertices: Any,
    edges: Any,
    face_edges: Any,
    frame: dict[str, Any],
    *,
    leg_fraction: float,
) -> tuple[dict[str, float | bool], dict[str, float | bool]]:
    contours = _section_contours(
        np,
        vertices,
        edges,
        face_edges,
        frame=frame,
        offset=-leg_fraction * float(frame["hipToKnee"]),
    )
    structural_length = float(frame["structuralLength"])
    candidates = [
        contour
        for contour in contours
        if contour["closed"] is True
        and structural_length * 0.025
        < float(contour["width"])
        < structural_length * 0.25
        and structural_length * 0.025
        < float(contour["depth"])
        < structural_length * 0.25
        and structural_length * 0.10 < float(contour["girth"]) < structural_length
    ]
    left_candidates = [
        contour for contour in candidates if float(contour["center"]) > 0.0
    ]
    right_candidates = [
        contour for contour in candidates if float(contour["center"]) < 0.0
    ]
    if not left_candidates or not right_candidates:
        raise ValueError("neutral MHR upper-thigh sections are unavailable")
    left = max(left_candidates, key=lambda contour: float(contour["girth"]))
    right = max(right_candidates, key=lambda contour: float(contour["girth"]))
    mean_girth = (float(left["girth"]) + float(right["girth"])) * 0.5
    if abs(float(left["girth"]) - float(right["girth"])) / max(mean_girth, 1e-8) > 0.35:
        raise ValueError("neutral MHR upper-thigh sections disagree")
    return left, right


def _region_evidence(
    np: Any,
    posed_keypoints: Any | None,
) -> dict[str, float]:
    defaults = {
        "breasts": 0.50,
        "waist": 0.50,
        "hips": 0.50,
        "glutes": 0.45,
        "thighs": 0.50,
    }
    if posed_keypoints is None:
        return defaults
    try:
        frame = _anatomical_frame(np, posed_keypoints)
    except ValueError:
        # View support is optional evidence. A difficult articulated pose must
        # not invalidate otherwise sound neutral identity geometry.
        return defaults
    front_support = min(1.0, abs(float(frame["front"][2])))
    side_support = min(1.0, abs(float(frame["lateral"][2])))
    return {
        "breasts": min(0.70, 0.40 + 0.18 * front_support + 0.12 * side_support),
        "waist": min(0.68, 0.41 + 0.17 * front_support + 0.10 * side_support),
        "hips": min(0.68, 0.42 + 0.18 * front_support + 0.08 * side_support),
        "glutes": min(0.68, 0.37 + 0.09 * front_support + 0.22 * side_support),
        "thighs": min(0.68, 0.43 + 0.18 * front_support + 0.07 * side_support),
    }


def derive_body_shape(
    vertices: Any,
    neutral_keypoints: Any,
    faces: Any,
    *,
    posed_keypoints: Any | None = None,
    np: Any,
) -> dict[str, object]:
    """Measure a pose-neutral MHR identity mesh below the shoulders.

    The result intentionally excludes face measurements.  ``posed_keypoints``
    only supplies a bounded camera-view evidence hint; all metric values come
    from the neutral mesh.
    """

    vertices_array = np.asarray(vertices, dtype=np.float64)
    keypoints_array = np.asarray(neutral_keypoints, dtype=np.float64)
    faces_array = np.asarray(faces)
    if (
        vertices_array.ndim != 2
        or vertices_array.shape[1:] != (3,)
        or len(vertices_array) < 4
        or keypoints_array.shape != (70, 3)
        or faces_array.ndim != 2
        or faces_array.shape[1:] != (3,)
        or len(faces_array) < 4
        or faces_array.dtype == np.dtype(bool)
        or not np.issubdtype(faces_array.dtype, np.integer)
        or not bool(np.isfinite(vertices_array).all())
        or not bool(np.isfinite(keypoints_array).all())
        or int(np.min(faces_array)) < 0
        or int(np.max(faces_array)) >= len(vertices_array)
    ):
        raise ValueError("neutral MHR shape geometry is invalid")
    posed_array: Any | None = None
    if posed_keypoints is not None:
        posed_array = np.asarray(posed_keypoints, dtype=np.float64)
        if posed_array.shape != (70, 3) or not bool(np.isfinite(posed_array).all()):
            raise ValueError("posed MHR keypoints are invalid")

    frame = _anatomical_frame(np, keypoints_array)
    edges, face_edges = _mesh_edges(np, faces_array)
    bust_fraction, bust = _scan_torso(
        np,
        vertices_array,
        edges,
        face_edges,
        frame,
        first=0.58,
        last=0.76,
        selector=lambda values: max(
            values,
            key=lambda item: float(item[1]["front"]),
        ),
    )
    underbust_fraction = max(0.50, min(0.64, bust_fraction - 0.14))
    underbust = _torso_section(
        np,
        vertices_array,
        edges,
        face_edges,
        frame,
        underbust_fraction,
    )
    waist_fraction, waist = _scan_torso(
        np,
        vertices_array,
        edges,
        face_edges,
        frame,
        first=0.34,
        last=0.58,
        selector=lambda values: min(
            values,
            key=lambda item: float(item[1]["girth"]),
        ),
    )
    seat_fraction, seat = _scan_torso(
        np,
        vertices_array,
        edges,
        face_edges,
        frame,
        first=-0.08,
        last=0.12,
        selector=lambda values: min(
            values,
            key=lambda item: float(item[1]["back"]),
        ),
    )
    thigh_fraction = 0.35
    left_thigh, right_thigh = _thigh_contours(
        np,
        vertices_array,
        edges,
        face_edges,
        frame,
        leg_fraction=thigh_fraction,
    )

    raw_values = {
        "bustGirth": float(bust["girth"]),
        "bustWidth": float(bust["width"]),
        "bustDepth": float(bust["depth"]),
        "underbustGirth": float(underbust["girth"]),
        "underbustWidth": float(underbust["width"]),
        "underbustDepth": float(underbust["depth"]),
        "breastGirthExcess": float(bust["girth"]) - float(underbust["girth"]),
        "breastDepthExcess": float(bust["depth"]) - float(underbust["depth"]),
        "breastProjection": float(bust["front"]) - float(underbust["front"]),
        "waistGirth": float(waist["girth"]),
        "waistWidth": float(waist["width"]),
        "waistDepth": float(waist["depth"]),
        "seatGirth": float(seat["girth"]),
        "seatWidth": float(seat["width"]),
        "seatDepth": float(seat["depth"]),
        "gluteProjection": float(waist["back"]) - float(seat["back"]),
        "upperThighGirth": (float(left_thigh["girth"]) + float(right_thigh["girth"]))
        * 0.5,
        "upperThighWidth": (float(left_thigh["width"]) + float(right_thigh["width"]))
        * 0.5,
        "upperThighDepth": (float(left_thigh["depth"]) + float(right_thigh["depth"]))
        * 0.5,
    }
    if set(raw_values) != set(BODY_SHAPE_METRICS):
        raise RuntimeError("body-shape metric implementation is incomplete")

    structural_length = float(frame["structuralLength"])
    thigh_sides = {
        "upperThighGirth": (
            float(left_thigh["girth"]),
            float(right_thigh["girth"]),
        ),
        "upperThighWidth": (
            float(left_thigh["width"]),
            float(right_thigh["width"]),
        ),
        "upperThighDepth": (
            float(left_thigh["depth"]),
            float(right_thigh["depth"]),
        ),
    }
    evidence = _region_evidence(np, posed_array)
    geometry_confidence = {
        "breasts": 1.0,
        "waist": 1.0,
        "hips": 1.0,
        "glutes": 1.0,
        "thighs": max(
            0.0,
            1.0
            - abs(float(left_thigh["girth"]) - float(right_thigh["girth"]))
            / max(raw_values["upperThighGirth"], 1e-8)
            / 0.35,
        ),
    }
    regions: dict[str, dict[str, float]] = {}
    for region in BODY_SHAPE_REGION_METRICS:
        geometry = max(0.0, min(1.0, geometry_confidence[region]))
        evidence_value = max(0.0, min(1.0, evidence[region]))
        regions[region] = {
            "geometryConfidence": _rounded(geometry),
            "evidenceConfidence": _rounded(evidence_value),
            "confidence": _rounded(min(geometry, evidence_value)),
        }

    measurements: dict[str, dict[str, float]] = {}
    for region, metrics in BODY_SHAPE_REGION_METRICS.items():
        confidence = regions[region]["confidence"]
        for metric in metrics:
            meters = raw_values[metric]
            item = {
                "meters": _rounded(meters),
                "ratio": _rounded(meters / structural_length),
                "confidence": confidence,
            }
            if metric in _BILATERAL_METRICS:
                item["leftMeters"] = _rounded(thigh_sides[metric][0])
                item["rightMeters"] = _rounded(thigh_sides[metric][1])
            measurements[metric] = item

    result: dict[str, object] = {
        "schema": BODY_SHAPE_SCHEMA,
        "space": BODY_SHAPE_SPACE,
        "normalizer": {
            "id": "structural-length",
            "meters": _rounded(structural_length),
        },
        "confidenceKind": BODY_SHAPE_CONFIDENCE_KIND,
        "measurements": measurements,
        "regions": regions,
        "planes": {
            "bustTorsoFraction": _rounded(bust_fraction),
            "underbustTorsoFraction": _rounded(underbust_fraction),
            "waistTorsoFraction": _rounded(waist_fraction),
            "seatTorsoFraction": _rounded(seat_fraction),
            "upperThighLegFraction": _rounded(thigh_fraction),
        },
        "overallConfidence": _rounded(
            sum(status["confidence"] for status in regions.values()) / len(regions)
        ),
    }
    validate_body_shape(result)
    return result


__all__ = ["derive_body_shape"]
