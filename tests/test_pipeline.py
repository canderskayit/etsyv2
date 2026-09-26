import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import server


class MockupCompletionTests(unittest.TestCase):
    def run_batch(self, count=2, video_error="", video=False, stop=False):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            prepared = root / "poster_2k_3x4.png"
            prepared.write_bytes(b"source")
            ready_root = root / "ready"
            ready_root.mkdir()
            output = ready_root / "poster"
            video_path = root / "video.mp4"
            video_path.write_bytes(b"video")
            stack.enter_context(patch.object(server, "external_ready_dir", return_value=ready_root))
            stack.enter_context(patch.object(server, "product_upload_dir", return_value=root / "uploads"))
            for name in ("add_event", "set_step", "update_product", "stop_photoshop_automation_processes", "terminate_photoshop_processes"):
                stack.enter_context(patch.object(server, name))
            stack.enter_context(patch.object(server, "requested_stop", return_value=stop))
            stack.enter_context(patch.object(server, "existing_queue_item_cancelled", return_value=False))
            stack.enter_context(patch.object(server, "video_file_is_valid", return_value=video))
            stack.enter_context(patch.object(server, "collect_external_outputs", return_value={
                "mockups": [root / f"{i}.png" for i in range(count)],
                "videos": [video_path] if video else [],
            }))
            copied = stack.enter_context(patch.object(
                server, "copy_external_assets",
                side_effect=lambda product, outputs, **kw: {
                    "mockups": len(outputs["mockups"]), "videos": len(outputs["videos"])
                },
            ))
            def launch(*args, **kwargs):
                output.mkdir()
                (output / prepared.name).write_bytes(b"source")
                Path(kwargs["env"]["CODEX_MOCKUP_STATUS_FILE"]).write_text(
                    json.dumps({"ok": True, "phase": "done", "video_error": video_error}),
                    encoding="utf-8",
                )
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            stack.enter_context(patch.object(server.subprocess, "run", side_effect=launch))
            # A completed script must not wait for the old 900-second timeout.
            stack.enter_context(patch.object(server.time, "sleep", side_effect=AssertionError("unexpected wait")))
            result = server.run_external_mockup_script("test", prepared, {}, only_psd_stems=["one", "two"])
            self.assertEqual(copied.call_count, 1)
            return result

    def test_completed_mockups_survive_video_error(self):
        result = self.run_batch(video_error="Photoshop scratch disk full")
        self.assertEqual(result["mockups"], 2)
        self.assertEqual(result["videos"], 0)
        self.assertIn("scratch disk", result["video_error"])

    def test_completed_video_is_saved(self):
        result = self.run_batch(video=True)
        self.assertEqual(result["videos"], 1)
        self.assertEqual(result["video_error"], "")

    def test_partial_mockup_batch_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError, "1/2"):
            self.run_batch(count=1)

    def test_stop_is_observed_before_output_wait(self):
        with self.assertRaises(server.StopJob):
            self.run_batch(stop=True)

    def test_retired_delivery_does_not_call_external_services(self):
        with patch.object(server, "build_digital_delivery_package", side_effect=AssertionError("retired integration")):
            self.assertTrue(server.prepare_and_sync_digital_delivery("test", "source")["skipped"])
        self.assertNotIn("google_drive", server.ACTIVE_STEP_KEYS)
        self.assertNotIn("digital_package", server.ACTIVE_STEP_KEYS)

    def test_preview_is_small_cached_and_preserves_original(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder, patch.object(server, "DATA", Path(folder)):
            source = Path(folder) / "original.png"
            Image.new("RGB", (3000, 4000), "orange").save(source)
            original = source.read_bytes()
            preview = server.panel_preview_path(source)
            modified = preview.stat().st_mtime_ns
            with Image.open(preview) as image:
                self.assertLessEqual(max(image.size), 720)
            self.assertEqual(server.panel_preview_path(source).stat().st_mtime_ns, modified)
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
