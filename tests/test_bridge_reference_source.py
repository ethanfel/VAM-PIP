from __future__ import annotations

from pathlib import Path
import unittest


class BridgeReferenceSourceTests(unittest.TestCase):
    @staticmethod
    def source() -> str:
        repository = Path(__file__).resolve().parents[1]
        return (
            repository
            / "src"
            / "vampip"
            / "bridge_assets"
            / "VAMPipBridge.cs"
        ).read_text(encoding="utf-8")

    def test_reference_surface_is_owned_bounded_and_published(self) -> None:
        source = self.source()

        for value in (
            '"showSam3dReference"',
            '"removeSam3dReference"',
            '"ImagePanelEmissive"',
            '"VAMPip SAM3D Reference"',
            '"Custom/Images/VAMPip/SAM3D/"',
            '"sam3d-reference-v1"',
        ):
            self.assertIn(value, source)
        self.assertIn("Sam3dReferenceMaximumBytes", source)
        self.assertIn("Sam3dReferenceMaximumDimension", source)
        self.assertIn("ValidateSam3dReferenceFile(request);", source)
        self.assertIn("Sha256Bytes(payload)", source)
        self.assertIn("IsOwnedSam3dReferencePath", source)
        self.assertIn("reference.SetOn(true);", source)
        self.assertIn("current.SetOn(snapshot.On);", source)
        self.assertNotIn(
            '(existingUrl ?? "").Trim().Length != 0 &&',
            source,
        )
        self.assertIn('sam3d["reference"] =', source)
        status_start = source.index("private JSONClass BuildSam3dReferenceStatus()")
        status_end = source.index(
            "private static JSONArray Capabilities()",
            status_start,
        )
        status = source[status_start:status_end]
        self.assertIn('"body-fit"', status)
        self.assertIn('"pose-aligned"', status)
        self.assertIn('result["alignedToPose"]', status)
        self.assertIn('result["jobRevision"]', status)

    def test_reference_creation_is_cleaned_if_a_coroutine_is_cancelled(
        self,
    ) -> None:
        source = self.source()
        stop_start = source.index("private void StopBridgeWorkForLifecycle(")
        stop_end = source.index("private void Update()", stop_start)
        stop = source[stop_start:stop_end]
        ensure_start = source.index("private IEnumerator EnsureSam3dReference(")
        ensure_end = source.index(
            "private string RemoveCreatedSam3dReference(",
            ensure_start,
        )
        ensure = source[ensure_start:ensure_end]
        actions_start = source.index("private IEnumerator ExecuteApplySam3dResult(")
        actions_end = source.index(
            "private IEnumerator ExecuteRemoveSam3dReference(",
            actions_start,
        )
        actions = source[actions_start:actions_end]

        self.assertIn("_inFlightSam3dReferenceRequest", stop)
        self.assertIn("_inFlightSam3dReferenceResult", stop)
        self.assertIn("RemoveInFlightCreatedSam3dReference();", stop)
        self.assertLess(
            stop.index("StopAllCoroutines();"),
            stop.index("RemoveInFlightCreatedSam3dReference();"),
        )
        ownership = (
            "// From this point onward the fixed UID belongs to this\n"
            "                // transaction, even if VaM fails part-way "
            "through creation.\n"
            "                result.Created = true;"
        )
        self.assertIn(ownership, ensure)
        self.assertLess(
            ensure.index("result.Created = true;"),
            ensure.index("while (true)"),
        )
        self.assertGreaterEqual(
            actions.count("_inFlightSam3dReferenceRequest = request;"),
            2,
        )
        self.assertGreaterEqual(
            actions.count("ClearInFlightSam3dReference("),
            4,
        )

    def test_pose_apply_and_undo_include_the_reference_snapshot(self) -> None:
        source = self.source()
        snapshot_start = source.index(
            "private static Sam3dUndoSnapshot SnapshotSam3dState("
        )
        snapshot_end = source.index(
            "private static void BeginSam3dPoseTransaction(",
            snapshot_start,
        )
        snapshot = source[snapshot_start:snapshot_end]
        restore_start = source.index(
            "private static bool RestoreSam3dSnapshotContents("
        )
        restore_end = source.index(
            "private static void SnapSam3dControllerPhysicalPose(",
            restore_start,
        )
        restore = source[restore_start:restore_end]
        apply_start = source.index(
            "private static void ApplySam3dTransformContents("
        )
        apply_end = source.index(
            "private void FinishSam3dActionOk(",
            apply_start,
        )
        apply = source[apply_start:apply_end]

        self.assertIn("snapshot.Reference =", snapshot)
        self.assertIn("SnapshotSam3dReference(", snapshot)
        self.assertIn("snapshot.PreviousReferenceState =", snapshot)
        restore_wrapper_start = source.index(
            "private void RestoreSam3dSnapshot("
        )
        restore_with_wrapper = source[restore_wrapper_start:restore_end]
        self.assertIn("RestoreSam3dReferenceSnapshot(", restore)
        self.assertIn("_sam3dReferenceState =", restore_with_wrapper)
        self.assertIn("ConfigureSam3dReference(", apply)
        self.assertIn("request.Sam3dKeepReference", source)


if __name__ == "__main__":
    unittest.main()
