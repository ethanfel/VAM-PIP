from __future__ import annotations

import math
import unittest

from vampip.service import (
    ManagerService,
    _public_sam3d_status,
)


def transform(seed: float) -> dict[str, object]:
    return {
        "position": {
            "x": seed,
            "y": seed + 1,
            "z": seed + 2,
            "private": "drop",
        },
        "rotation": {
            "x": 0.0,
            "y": 0.5,
            "z": 0.0,
            "w": 0.866,
            "private": "drop",
        },
        "private": "drop",
    }


def settlement() -> dict[str, object]:
    return {
        "schema": 1,
        "requestId": "A" * 32,
        "capturedAtUtc": "2026-07-29T12:34:56.123Z",
        "settleFrames": 5,
        "controllerLimit": 2,
        "error": "",
        "available": True,
        "controllers": [
            {
                "id": "headControl",
                "requested": transform(1.0),
                "actual": transform(1.01),
                "positionErrorMeters": 0.01,
                "rotationErrorDegrees": 0.25,
                "state": {
                    "position": "On",
                    "rotation": "Comply",
                    "physicsEnabled": True,
                    "possessed": False,
                    "startedPossess": False,
                    "isGrabbing": True,
                    "private": True,
                },
                "private": "drop",
            },
            {
                "id": "neckControl",
                "requested": transform(-2.0),
                "actual": transform(-1.99),
                "positionErrorMeters": 0.02,
                "rotationErrorDegrees": 0.5,
                "state": {
                    "position": "On",
                    "rotation": "On",
                    "physicsEnabled": False,
                    "possessed": False,
                    "startedPossess": False,
                    "isGrabbing": False,
                },
            },
            {"id": "hipControl", "requested": transform(0.0)},
        ],
        "private": "drop",
    }


def stringified_bridge_settlement() -> dict[str, object]:
    def stringify(value: object) -> object:
        if isinstance(value, bool):
            return "TrUe" if value else "fAlSe"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, dict):
            return {key: stringify(item) for key, item in value.items()}
        if isinstance(value, list):
            return [stringify(item) for item in value]
        return value

    result = stringify(settlement())
    assert isinstance(result, dict)
    return result


class Sam3dSettlementPublicStatusTests(unittest.TestCase):
    def test_settlement_is_fixed_bounded_and_allowlisted(self) -> None:
        status = _public_sam3d_status(
            {
                "applied": True,
                "undoAvailable": True,
                "settlement": settlement(),
            }
        )

        self.assertIsNotNone(status)
        public = status["settlement"]
        self.assertEqual(
            set(public),
            {
                "schema",
                "requestId",
                "capturedAtUtc",
                "settleFrames",
                "controllerLimit",
                "error",
                "available",
                "controllers",
            },
        )
        self.assertEqual(public["requestId"], "a" * 32)
        self.assertEqual(public["controllerLimit"], 2)
        self.assertEqual(
            [item["id"] for item in public["controllers"]],
            ["headControl", "neckControl"],
        )
        head = public["controllers"][0]
        self.assertEqual(
            set(head),
            {
                "id",
                "requested",
                "actual",
                "positionErrorMeters",
                "rotationErrorDegrees",
                "state",
            },
        )
        self.assertEqual(
            set(head["requested"]),
            {"position", "rotation"},
        )
        self.assertEqual(
            set(head["requested"]["position"]),
            {"x", "y", "z"},
        )
        self.assertEqual(
            set(head["requested"]["rotation"]),
            {"x", "y", "z", "w"},
        )
        self.assertEqual(
            set(head["state"]),
            {
                "position",
                "rotation",
                "physicsEnabled",
                "possessed",
                "startedPossess",
                "isGrabbing",
            },
        )

    def test_stringified_simplejson_values_are_strictly_normalized(self) -> None:
        raw = stringified_bridge_settlement()
        raw["controllers"][0]["positionErrorMeters"] = "1e-2"
        raw["controllers"][0]["rotationErrorDegrees"] = "2.5E-1"

        status = _public_sam3d_status(
            {
                "applied": True,
                "undoAvailable": True,
                "settlement": raw,
            }
        )

        public = status["settlement"]
        self.assertTrue(public["available"])
        self.assertEqual(public["schema"], 1)
        self.assertEqual(public["settleFrames"], 5)
        self.assertEqual(public["controllerLimit"], 2)
        head = public["controllers"][0]
        self.assertEqual(head["positionErrorMeters"], 0.01)
        self.assertEqual(head["rotationErrorDegrees"], 0.25)
        self.assertEqual(head["requested"]["position"]["x"], 1.0)
        self.assertIs(head["state"]["physicsEnabled"], True)
        self.assertIs(head["state"]["possessed"], False)

    def test_invalid_or_unbounded_values_are_not_exposed(self) -> None:
        raw = settlement()
        raw.update(
            {
                "requestId": "../not-a-token",
                "capturedAtUtc": "not-a-timestamp",
                "settleFrames": 10_000,
                "controllerLimit": 100,
            }
        )
        raw["controllers"] = [
            {
                "id": "headControl",
                "requested": {
                    "position": {"x": math.nan, "y": 0, "z": 0},
                    "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                },
                "actual": {
                    "position": {"x": 0, "y": 0, "z": 0},
                    "rotation": {"x": 2, "y": 0, "z": 0, "w": 1},
                },
                "positionErrorMeters": math.inf,
                "rotationErrorDegrees": 10**10_000,
                "state": {
                    "position": "../../On",
                    "rotation": "Comply",
                    "physicsEnabled": " true ",
                    "possessed": False,
                },
            },
            {"id": "headControl", "requested": transform(0.0)},
            {"id": "neckControl", "requested": transform(0.0)},
        ]

        status = _public_sam3d_status(
            {
                "applied": True,
                "undoAvailable": True,
                "settlement": raw,
            }
        )

        public = status["settlement"]
        self.assertNotIn("requestId", public)
        self.assertNotIn("capturedAtUtc", public)
        self.assertEqual(public["settleFrames"], 0)
        self.assertEqual(public["controllerLimit"], 0)
        self.assertFalse(public["available"])
        self.assertEqual(len(public["controllers"]), 1)
        head = public["controllers"][0]
        self.assertEqual(
            head,
            {
                "id": "headControl",
                "state": {
                    "rotation": "Comply",
                    "possessed": False,
                },
            },
        )

    def test_unknown_settlement_schema_is_ignored(self) -> None:
        raw = settlement()
        raw["schema"] = 2

        status = _public_sam3d_status(
            {
                "applied": True,
                "undoAvailable": True,
                "settlement": raw,
            }
        )

        self.assertNotIn("settlement", status)


class Sam3dSettlementJobDecorationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = object.__new__(ManagerService)
        self.job_id = "1" * 32
        self.revision = "2" * 32
        self.document = {
            "id": self.job_id,
            "settlement": {"private": "stale"},
            "last_vam_action": {
                "action": "apply",
                "request_id": "3" * 32,
                "revision": self.revision,
                "target_uid": "Person",
                "camera_uid": "SAM Camera",
                "state": "succeeded",
                "message": "Applied.",
            },
        }
        self.live = {
            "applied": True,
            "undoAvailable": True,
            "jobId": self.job_id,
            "revision": self.revision,
            "targetUid": "Person",
            "cameraUid": "SAM Camera",
            "settlement": settlement(),
        }

    def test_matching_applied_job_includes_settlement(self) -> None:
        decorated = self.service._decorate_sam3d_job(
            self.document,
            {"sam3d": self.live},
        )

        self.assertEqual(decorated["settlement"]["schema"], 1)
        self.assertEqual(
            [item["id"] for item in decorated["settlement"]["controllers"]],
            ["headControl", "neckControl"],
        )

    def test_stale_or_other_job_settlement_is_not_included(self) -> None:
        cases = (
            ("not-applied", {"applied": False}),
            ("other-job", {"jobId": "4" * 32}),
            ("other-revision", {"revision": "5" * 32}),
        )
        for name, update in cases:
            with self.subTest(name=name):
                live = dict(self.live)
                live.update(update)
                decorated = self.service._decorate_sam3d_job(
                    self.document,
                    {"sam3d": live},
                )
                self.assertNotIn("settlement", decorated)


if __name__ == "__main__":
    unittest.main()
