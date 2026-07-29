from __future__ import annotations

import unittest
from pathlib import Path


RENDERER_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "vampip"
    / "renderer_assets"
    / "VRRendererX"
    / "src"
    / "vamrobot_VRVideoAndFunscriptExporter.cs"
)


class VAMPipRendererCaptureLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RENDERER_SOURCE.read_text(encoding="utf-8-sig")

    def test_all_capture_completion_uses_the_central_finish_path(self) -> None:
        finish = self.source[
            self.source.index("private void FinishVAMPipCapture(") :
            self.source.index("private void AbortVAMPipCapture(")
        ]
        self.assertIn("RestoreVAMPipCaptureNames();", finish)
        self.assertIn("vampipCaptureInProgress = false;", finish)
        self.assertIn("vampipCaptureAwaitingEncode = false;", finish)
        self.assertIn("vampipActiveCaptureGeneration = 0;", finish)
        self.assertIn("PublishVAMPipTerminalResult(succeeded, output, error);", finish)

        ready = self.source[
            self.source.index("private void FinalizeVAMPipCaptureIfReady(") :
            self.source.index("public override void Init()")
        ]
        self.assertIn("FinishVAMPipCapture(succeeded, output, error);", ready)

    def test_early_end_render_and_lifecycle_interruptions_abort_capture(self) -> None:
        end_render = self.source[
            self.source.index("void EndRender()") :
            self.source.index("private Camera CreateFlatCamera(")
        ]
        abort_guard = end_render.index(
            "if (vampipCaptureInProgress && !vampipCaptureFinalizationInProgress)"
        )
        normal_exit = end_render.index("if (!bRendering)")
        self.assertLess(abort_guard, normal_exit)
        self.assertIn(
            'AbortVAMPipCapture("Capture was cancelled before it completed.");',
            end_render,
        )
        self.assertIn("private void OnDisable()", self.source)
        self.assertIn(
            'AbortVAMPipCapture("Capture render failed: " + e.Message);',
            self.source,
        )

    def test_late_encoder_result_is_bound_to_capture_generation(self) -> None:
        publisher = self.source[
            self.source.index("private void PublishVAMPipEncodeResult(") :
            self.source.index("private void ReleaseVAMPipEncoderThread(")
        ]
        self.assertIn("generation != vampipActiveCaptureGeneration", publisher)
        self.assertIn(
            "ReleaseVAMPipEncoderThread(threadIdx, captureFreeFlags, captureSemaphore);",
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
