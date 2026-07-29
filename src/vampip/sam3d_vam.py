from __future__ import annotations

import hashlib
import json
import math
SAM3D_SOLUTION_SCHEMA = 1
MHR70_NAMES = (
    "nose",
    "left-eye",
    "right-eye",
    "left-ear",
    "right-ear",
    "left-shoulder",
    "right-shoulder",
    "left-elbow",
    "right-elbow",
    "left-hip",
    "right-hip",
    "left-knee",
    "right-knee",
    "left-ankle",
    "right-ankle",
    "left-big-toe-tip",
    "left-small-toe-tip",
    "left-heel",
    "right-big-toe-tip",
    "right-small-toe-tip",
    "right-heel",
    "right-thumb-tip",
    "right-thumb-first-joint",
    "right-thumb-second-joint",
    "right-thumb-third-joint",
    "right-index-tip",
    "right-index-first-joint",
    "right-index-second-joint",
    "right-index-third-joint",
    "right-middle-tip",
    "right-middle-first-joint",
    "right-middle-second-joint",
    "right-middle-third-joint",
    "right-ring-tip",
    "right-ring-first-joint",
    "right-ring-second-joint",
    "right-ring-third-joint",
    "right-pinky-tip",
    "right-pinky-first-joint",
    "right-pinky-second-joint",
    "right-pinky-third-joint",
    "right-wrist",
    "left-thumb-tip",
    "left-thumb-first-joint",
    "left-thumb-second-joint",
    "left-thumb-third-joint",
    "left-index-tip",
    "left-index-first-joint",
    "left-index-second-joint",
    "left-index-third-joint",
    "left-middle-tip",
    "left-middle-first-joint",
    "left-middle-second-joint",
    "left-middle-third-joint",
    "left-ring-tip",
    "left-ring-first-joint",
    "left-ring-second-joint",
    "left-ring-third-joint",
    "left-pinky-tip",
    "left-pinky-first-joint",
    "left-pinky-second-joint",
    "left-pinky-third-joint",
    "left-wrist",
    "left-olecranon",
    "right-olecranon",
    "left-cubital-fossa",
    "right-cubital-fossa",
    "left-acromion",
    "right-acromion",
    "neck",
)

VAM_CONTROLLER_IDS = frozenset(
    {
        "hipControl",
        "abdomen2Control",
        "chestControl",
        "neckControl",
        "headControl",
        "lShoulderControl",
        "rShoulderControl",
        "lArmControl",
        "rArmControl",
        "lElbowControl",
        "rElbowControl",
        "lHandControl",
        "rHandControl",
        "lThighControl",
        "rThighControl",
        "lKneeControl",
        "rKneeControl",
        "lFootControl",
        "rFootControl",
    }
)

VR_RENDERER_RESOLUTIONS: dict[str, dict[str, tuple[int, int]]] = {
    "36:9": {
        "1600x400": (1600, 400),
        "3200x800": (3200, 800),
        "6400x1600": (6400, 1600),
    },
    "32:9": {
        "2048x576": (2048, 576),
        "2560x720": (2560, 720),
        "3840x1080 (DFHD)": (3840, 1080),
        "5120x1440 (DQHD)": (5120, 1440),
        "7680x2160 (DUHD)": (7680, 2160),
    },
    "21:9": {
        "2560x1080 (WFHD)": (2560, 1080),
        "3440x1440 (WQHD)": (3440, 1440),
        "5120x2160 (4K WUHD)": (5120, 2160),
    },
    "16:9": {
        "1280x720 (HD)": (1280, 720),
        "1920x1080 (FHD)": (1920, 1080),
        "2560x1440 (QHD)": (2560, 1440),
        "3840x2160 (4K UHD)": (3840, 2160),
        "5120x2880 (5K)": (5120, 2880),
        "7680x4320 (8K UHD)": (7680, 4320),
    },
    "16:10": {
        "1280x800 (WXGA)": (1280, 800),
        "1440x900 (WXGA+)": (1440, 900),
        "1920x1200 (WUXGA)": (1920, 1200),
        "3840x2400 (2x WUXGA)": (3840, 2400),
    },
    "4:3": {
        "800x600 (SVGA)": (800, 600),
        "1024x768 (XGA)": (1024, 768),
        "2048x1536 (2x XGA)": (2048, 1536),
        "4096x3072 (4x XGA)": (4096, 3072),
    },
    "2:1": {
        "1280x640": (1280, 640),
        "1920x960": (1920, 960),
        "2560x1280": (2560, 1280),
        "3840x1920 (4K)": (3840, 1920),
        "5120x2560 (5K)": (5120, 2560),
        "7680x3840 (8K)": (7680, 3840),
    },
    "1:1": {
        "256x256": (256, 256),
        "512x512": (512, 512),
        "1024x1024": (1024, 1024),
        "1920x1920": (1920, 1920),
        "2048x2048": (2048, 2048),
        "2560x2560": (2560, 2560),
        "3840x3840 (4K)": (3840, 3840),
        "4096x4096": (4096, 4096),
    },
}

Vector = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]

# VaM's headControl pivot sits inside the skull rather than on a visible facial
# landmark. These measured bind offsets are normalized by character height;
# the inferred face frame rotates them into the source pose.
_VAM_HEAD_UP_PER_HEIGHT = 0.0655
_VAM_HEAD_FORWARD_PER_HEIGHT = 0.0045


def sam3d_solution_revision(document: dict[str, object]) -> str:
    """Return the canonical revision for a bridge solution document."""

    if not isinstance(document, dict):
        raise TypeError("SAM3D solution must be an object")
    unsigned = dict(document)
    unsigned.pop("revision", None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:32]


def _finite_vector(value: object, *, size: int, label: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"{label} must contain exactly {size} numbers")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{label} must contain only finite numbers")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError(f"{label} must contain only finite numbers")
        result.append(number)
    return tuple(result)


def _add(a: Vector, b: Vector) -> Vector:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vector, b: Vector) -> Vector:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(value: Vector, scalar: float) -> Vector:
    return (value[0] * scalar, value[1] * scalar, value[2] * scalar)


def _dot(a: Vector, b: Vector) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vector, b: Vector) -> Vector:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(value: Vector) -> float:
    return math.sqrt(_dot(value, value))


def _unit(value: Vector, fallback: Vector) -> Vector:
    length = _length(value)
    if length < 1e-8:
        return fallback
    return _mul(value, 1.0 / length)


def _mean(*values: Vector) -> Vector:
    if not values:
        raise ValueError("at least one vector is required")
    divisor = float(len(values))
    return (
        sum(value[0] for value in values) / divisor,
        sum(value[1] for value in values) / divisor,
        sum(value[2] for value in values) / divisor,
    )


def _lerp(a: Vector, b: Vector, amount: float) -> Vector:
    return _add(a, _mul(_sub(b, a), amount))


def _quat_normalize(value: Quaternion) -> Quaternion:
    length = math.sqrt(sum(component * component for component in value))
    if length < 1e-8:
        return (0.0, 0.0, 0.0, 1.0)
    result = tuple(component / length for component in value)
    return (result[0], result[1], result[2], result[3])


def _quat_multiply(a: Quaternion, b: Quaternion) -> Quaternion:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return _quat_normalize(
        (
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        )
    )


def _quat_from_to(source: Vector, target: Vector) -> Quaternion:
    source = _unit(source, (0.0, 1.0, 0.0))
    target = _unit(target, source)
    dot = max(-1.0, min(1.0, _dot(source, target)))
    if dot > 1.0 - 1e-8:
        return (0.0, 0.0, 0.0, 1.0)
    if dot < -1.0 + 1e-8:
        axis = _cross(source, (1.0, 0.0, 0.0))
        if _length(axis) < 1e-6:
            axis = _cross(source, (0.0, 1.0, 0.0))
        axis = _unit(axis, (0.0, 0.0, 1.0))
        return (axis[0], axis[1], axis[2], 0.0)
    axis = _cross(source, target)
    return _quat_normalize((axis[0], axis[1], axis[2], 1.0 + dot))


def _quat_from_basis(x_axis: Vector, y_axis: Vector, z_axis: Vector) -> Quaternion:
    # Columns are the transformed canonical +X/+Y/+Z basis vectors.
    m00, m10, m20 = x_axis
    m01, m11, m21 = y_axis
    m02, m12, m22 = z_axis
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        return _quat_normalize(
            ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s)
        )
    if m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        return _quat_normalize(
            (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
        )
    if m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        return _quat_normalize(
            ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
        )
    s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
    return _quat_normalize(
        ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)
    )


def _body_axes(points: dict[str, Vector]) -> tuple[Vector, Vector, Vector]:
    pelvis = _mean(points["left-hip"], points["right-hip"])
    shoulders = _mean(points["left-shoulder"], points["right-shoulder"])
    # MHR semantic right/left preserves a body's own lateral direction even
    # when that body faces the source camera.
    right = _unit(
        _sub(points["right-hip"], points["left-hip"]),
        (1.0, 0.0, 0.0),
    )
    up = _unit(_sub(shoulders, pelvis), (0.0, 1.0, 0.0))
    forward = _unit(_cross(right, up), (0.0, 0.0, 1.0))
    right = _unit(_cross(up, forward), right)
    forward = _unit(_cross(right, up), forward)
    return right, up, forward


def _head_axes(
    points: dict[str, Vector],
    fallback: tuple[Vector, Vector, Vector],
) -> tuple[Vector, Vector, Vector]:
    """Build a complete anatomical frame from stable facial landmarks."""

    fallback_right, fallback_up, fallback_forward = fallback
    ear_mid = _mean(points["left-ear"], points["right-ear"])
    eye_mid = _mean(points["left-eye"], points["right-eye"])

    right_raw = _sub(points["right-ear"], points["left-ear"])
    if _length(right_raw) < 1e-6:
        right_raw = _sub(points["right-eye"], points["left-eye"])
    if _length(right_raw) < 1e-6:
        return fallback
    right = _unit(right_raw, fallback_right)

    # Eye-to-ear depth provides pitch while the nose disambiguates which side
    # of the face is forward. Remove the lateral component before normalizing.
    forward_raw = _sub(eye_mid, ear_mid)
    forward_raw = _sub(forward_raw, _mul(right, _dot(forward_raw, right)))
    nose_direction = _sub(points["nose"], ear_mid)
    nose_direction = _sub(
        nose_direction,
        _mul(right, _dot(nose_direction, right)),
    )
    if _length(forward_raw) < 1e-6:
        forward_raw = nose_direction
    if _length(forward_raw) < 1e-6:
        return fallback
    forward = _unit(forward_raw, fallback_forward)
    if _dot(forward, nose_direction) < 0.0:
        forward = _mul(forward, -1.0)

    up_raw = _cross(forward, right)
    if _length(up_raw) < 1e-6:
        return fallback
    up = _unit(up_raw, fallback_up)

    right = _unit(_cross(up, forward), right)
    forward = _unit(_cross(right, up), forward)
    return right, up, forward


def _cv_to_unity(value: Vector) -> Vector:
    # SAM uses x-right/y-down/z-forward camera coordinates. VaM/Unity uses
    # x-right/y-up/z-forward for the bridge contract.
    return (value[0], -value[1], value[2])


def _controller(
    controller_id: str,
    position: Vector,
    rotation: Quaternion,
) -> dict[str, object]:
    if controller_id not in VAM_CONTROLLER_IDS:
        raise ValueError("controller ID is not allowlisted")
    if max(map(abs, position)) > 5.0:
        raise ValueError("retargeted controller position is out of bounds")
    return {
        "id": controller_id,
        "position": [round(component, 7) for component in position],
        "rotation": [round(component, 8) for component in _quat_normalize(rotation)],
    }


def _segment_rotation(
    start: Vector,
    end: Vector,
    rest_direction: Vector,
) -> Quaternion:
    return _quat_from_to(rest_direction, _sub(end, start))


def _stature_scale(points: dict[str, Vector], desired_height: float) -> float:
    pelvis = _mean(points["left-hip"], points["right-hip"])
    neck = points["neck"]
    head = _mean(
        points["nose"],
        points["left-eye"],
        points["right-eye"],
        points["left-ear"],
        points["right-ear"],
    )
    leg_lengths = []
    for side in ("left", "right"):
        leg_lengths.append(
            _length(_sub(points[f"{side}-knee"], points[f"{side}-hip"]))
            + _length(_sub(points[f"{side}-ankle"], points[f"{side}-knee"]))
        )
    raw_height = (
        _length(_sub(neck, pelvis))
        + sum(leg_lengths) / len(leg_lengths)
        + 1.7 * _length(_sub(head, neck))
        + 0.08 * (sum(leg_lengths) / len(leg_lengths))
    )
    if raw_height < 1e-5:
        raise ValueError("SAM 3D Body returned a degenerate skeleton")
    scale = desired_height / raw_height
    if not math.isfinite(scale) or scale <= 0.0 or scale > 100.0:
        raise ValueError("SAM 3D Body skeleton scale is invalid")
    return scale


def _points_from_person(person: dict[str, object]) -> tuple[dict[str, Vector], Vector]:
    raw = person.get("keypoints3d")
    if not isinstance(raw, list) or len(raw) != len(MHR70_NAMES):
        raise ValueError("SAM 3D Body result must contain 70 three-dimensional keypoints")
    cv_points = {
        name: _finite_vector(value, size=3, label=f"keypoints3d[{index}]")
        for index, (name, value) in enumerate(zip(MHR70_NAMES, raw))
    }
    points = {
        name: _cv_to_unity((value[0], value[1], value[2]))
        for name, value in cv_points.items()
    }
    pelvis_cv = _mean(cv_points["left-hip"], cv_points["right-hip"])
    return points, pelvis_cv


def build_vam_solution(
    manifest: dict[str, object],
    *,
    job_id: str,
    person_index: int = 0,
    height_m: float = 1.65,
    aspect_ratio: str = "16:9",
    output_resolution: str = "1280x720 (HD)",
    image_format: str = "jpeg",
    horizontal_fov: float | None = None,
    basename: str | None = None,
) -> dict[str, object]:
    """Convert one SAM3D result into the bounded bridge solution schema.

    Positions are hip-relative metre offsets in Unity axes. The VaM bridge
    owns the final selected-Person hip anchor and yaw transform.
    """

    if (
        not isinstance(job_id, str)
        or len(job_id) != 32
        or any(character not in "0123456789abcdef" for character in job_id)
    ):
        raise ValueError("job_id must be a lowercase 32-character opaque token")
    if isinstance(person_index, bool) or not isinstance(person_index, int):
        raise TypeError("person_index must be an integer")
    if isinstance(height_m, bool) or not isinstance(height_m, (int, float)):
        raise TypeError("height_m must be a number")
    height_m = float(height_m)
    if not math.isfinite(height_m) or height_m < 0.5 or height_m > 3.0:
        raise ValueError("height_m must be between 0.5 and 3.0")

    source = manifest.get("source")
    people = manifest.get("people")
    if not isinstance(source, dict) or not isinstance(people, list):
        raise ValueError("SAM 3D Body manifest is incomplete")
    if person_index < 0 or person_index >= len(people):
        raise ValueError("person_index is not available in this SAM3D result")
    person = people[person_index]
    if not isinstance(person, dict):
        raise ValueError("SAM 3D Body person result is invalid")

    width = source.get("width")
    height = source.get("height")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or isinstance(height, bool)
        or not isinstance(height, int)
        or width < 1
        or height < 1
    ):
        raise ValueError("SAM 3D Body source dimensions are invalid")
    if not isinstance(aspect_ratio, str) or aspect_ratio not in VR_RENDERER_RESOLUTIONS:
        raise ValueError("aspect_ratio is not supported by VRRendererX")
    if not isinstance(output_resolution, str):
        raise TypeError("output_resolution must be a renderer choice string")
    try:
        output_width, output_height = VR_RENDERER_RESOLUTIONS[aspect_ratio][
            output_resolution
        ]
    except KeyError as error:
        raise ValueError(
            "output_resolution is not valid for the selected aspect_ratio"
        ) from error
    if output_width * output_height > 50_000_000:
        raise ValueError("output_resolution exceeds the safe render pixel limit")
    if image_format not in {"jpeg", "png"}:
        raise ValueError("image_format must be jpeg or png")
    required_basename = job_id
    if basename is None:
        basename = required_basename
    if basename != required_basename:
        raise ValueError("basename is fixed by the SAM3D job identity")
    if (
        not isinstance(basename, str)
        or len(basename) < 1
        or len(basename) > 80
        or not basename[0].isalnum()
        or any(not (character.isalnum() or character in "-_") for character in basename)
    ):
        raise ValueError(
            "basename must contain only letters, numbers, '-' and '_'"
        )

    raw_points, pelvis_cv = _points_from_person(person)
    scale = _stature_scale(raw_points, height_m)
    pelvis = _mean(raw_points["left-hip"], raw_points["right-hip"])
    points = {
        name: _mul(_sub(value, pelvis), scale)
        for name, value in raw_points.items()
    }
    shoulder_mid = _mean(points["left-shoulder"], points["right-shoulder"])
    torso_axes = _body_axes(points)
    torso_rotation = _quat_from_basis(*torso_axes)
    head_axes = _head_axes(points, torso_axes)
    head_rotation = _quat_from_basis(*head_axes)
    head = _add(
        points["neck"],
        _add(
            _mul(head_axes[1], height_m * _VAM_HEAD_UP_PER_HEIGHT),
            _mul(head_axes[2], height_m * _VAM_HEAD_FORWARD_PER_HEIGHT),
        ),
    )

    controller_values: list[dict[str, object]] = [
        _controller("hipControl", (0.0, 0.0, 0.0), torso_rotation),
        _controller(
            "abdomen2Control",
            _lerp((0.0, 0.0, 0.0), shoulder_mid, 0.38),
            torso_rotation,
        ),
        _controller(
            "chestControl",
            _lerp((0.0, 0.0, 0.0), shoulder_mid, 0.72),
            torso_rotation,
        ),
        _controller("neckControl", points["neck"], torso_rotation),
        _controller(
            "headControl",
            head,
            head_rotation,
        ),
    ]

    for side, vam_side, rest_side in (
        ("left", "l", (-1.0, 0.0, 0.0)),
        ("right", "r", (1.0, 0.0, 0.0)),
    ):
        shoulder = points[f"{side}-shoulder"]
        elbow = points[f"{side}-elbow"]
        wrist = points[f"{side}-wrist"]
        hip = points[f"{side}-hip"]
        knee = points[f"{side}-knee"]
        ankle = points[f"{side}-ankle"]
        toe = _mean(
            points[f"{side}-big-toe-tip"],
            points[f"{side}-small-toe-tip"],
        )
        controller_values.extend(
            [
                _controller(
                    f"{vam_side}ShoulderControl",
                    _lerp(points["neck"], shoulder, 0.2),
                    _segment_rotation(points["neck"], shoulder, rest_side),
                ),
                _controller(
                    f"{vam_side}ArmControl",
                    shoulder,
                    _segment_rotation(shoulder, elbow, rest_side),
                ),
                _controller(
                    f"{vam_side}ElbowControl",
                    elbow,
                    _segment_rotation(elbow, wrist, rest_side),
                ),
                _controller(
                    f"{vam_side}HandControl",
                    wrist,
                    _segment_rotation(
                        wrist,
                        points[f"{side}-middle-tip"],
                        rest_side,
                    ),
                ),
                _controller(
                    f"{vam_side}ThighControl",
                    hip,
                    _segment_rotation(hip, knee, (0.0, -1.0, 0.0)),
                ),
                _controller(
                    f"{vam_side}KneeControl",
                    knee,
                    _segment_rotation(knee, ankle, (0.0, -1.0, 0.0)),
                ),
                _controller(
                    f"{vam_side}FootControl",
                    ankle,
                    _segment_rotation(ankle, toe, (0.0, 0.0, 1.0)),
                ),
            ]
        )

    camera_translation = _finite_vector(
        person.get("predCamT"),
        size=3,
        label="predCamT",
    )
    camera_cv = (
        -(camera_translation[0] + pelvis_cv[0]),
        -(camera_translation[1] + pelvis_cv[1]),
        -(camera_translation[2] + pelvis_cv[2]),
    )
    camera_position = _mul(_cv_to_unity(camera_cv), scale)
    if max(map(abs, camera_position)) > 10.0:
        raise ValueError("retargeted camera position is out of bounds")
    focal_length = person.get("focalLength")
    if (
        isinstance(focal_length, bool)
        or not isinstance(focal_length, (int, float))
        or not math.isfinite(float(focal_length))
        or float(focal_length) <= 0.0
    ):
        raise ValueError("SAM 3D Body focal length is invalid")
    inferred_horizontal_fov = math.degrees(
        2.0 * math.atan(width / (2.0 * float(focal_length)))
    )
    inferred_horizontal_fov = max(5.0, min(170.0, inferred_horizontal_fov))
    if horizontal_fov is None:
        horizontal_fov = inferred_horizontal_fov
    elif (
        isinstance(horizontal_fov, bool)
        or not isinstance(horizontal_fov, (int, float))
        or not math.isfinite(float(horizontal_fov))
        or float(horizontal_fov) < 5.0
        or float(horizontal_fov) > 170.0
    ):
        raise ValueError("horizontal_fov must be between 5 and 170 degrees")
    horizontal_fov = float(horizontal_fov)

    solution: dict[str, object] = {
        "schema": SAM3D_SOLUTION_SCHEMA,
        "jobId": job_id,
        "coordinateSpace": "selected-person-hip-relative",
        "units": "meters",
        "canonicalAxes": {
            "right": "+X",
            "up": "+Y",
            "forward": "+Z",
        },
        "personIndex": person_index,
        "targetHeight": round(height_m, 6),
        "controllers": controller_values,
        "camera": {
            "position": [round(component, 7) for component in camera_position],
            "rotation": [0.0, 0.0, 0.0, 1.0],
            "flatHorizontalFov": round(horizontal_fov, 6),
            "aspectRatio": aspect_ratio,
            "outputResolution": output_resolution,
            "imageFormat": image_format,
            "basename": basename,
        },
    }
    solution["revision"] = sam3d_solution_revision(solution)
    return solution
