from __future__ import annotations

import unittest
from pathlib import Path


RENDERER_ROOT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "vampip"
    / "renderer_assets"
    / "VRRendererX"
)
RENDERER_SOURCE = (
    RENDERER_ROOT
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

    def test_capture_write_does_not_request_a_secure_file_move(self) -> None:
        writer = self.source[
            self.source.index(
                "private void SaveVAMPipCaptureAsFileInternal("
            ) : self.source.index(
                "private void BeginVAMPipCaptureEncoding("
            )
        ]

        self.assertIn(
            "FileManagerSecure.WriteAllBytes(outputPath, bytes);",
            writer,
        )
        self.assertNotIn("_partial", writer)
        self.assertNotIn("MoveFile(", writer)
        self.assertNotIn("DeleteFile(", writer)

    def test_capture_uses_and_prepares_the_dedicated_screenshot_directory(
        self,
    ) -> None:
        self.assertIn(
            'VAMPIP_SCREENSHOT_DIRECTORY = "Saves/screenshots/VAMPip/"',
            self.source,
        )
        output_path = self.source[
            self.source.index("private string GetVAMPipOutputPath(") :
            self.source.index("private void PublishVAMPipEncodeResult(")
        ]
        self.assertIn("return VAMPIP_SCREENSHOT_DIRECTORY + filename", output_path)

        capture = self.source[
            self.source.index("private void TakeVAMPipSingleScreenshot(") :
            self.source.index("private string GetVAMPipOutputPath(")
        ]
        directory_check = capture.index(
            "FileManagerSecure.DirectoryExists(VAMPIP_SCREENSHOT_DIRECTORY)"
        )
        directory_create = capture.index(
            "FileManagerSecure.CreateDirectory(VAMPIP_SCREENSHOT_DIRECTORY)"
        )
        begin_render = capture.index("BeginRender();")
        self.assertLess(directory_check, directory_create)
        self.assertLess(directory_create, begin_render)

        self.assertIn(
            'SCREENSHOT_DIRECTORY = "Saves/VR_Videos_And_Funscripts/"',
            self.source,
        )

    def test_cslist_entries_are_existing_csharp_sources(self) -> None:
        entries = [
            line.strip()
            for line in (RENDERER_ROOT / "Eosin_VRRenderer.cslist")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]

        self.assertTrue(entries)
        for entry in entries:
            with self.subTest(entry=entry):
                self.assertTrue(entry.endswith(".cs"))
                self.assertTrue((RENDERER_ROOT / entry).is_file())


if __name__ == "__main__":
    unittest.main()
