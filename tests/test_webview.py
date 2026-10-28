import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime

from desktop_annotator.annotation import Annotation, load_document, render_annotation
from desktop_annotator.capture import TextCandidate
from desktop_annotator.webview import (
    AnnotatorWindow,
    annotations_from_payload,
    build_state,
    entries_payload,
    page_with_state,
)


def annotation(quote="quoted", comment="commented", source="Firefox", minute=1):
    return Annotation(
        quote=quote,
        comment=comment,
        source=source,
        captured_at=datetime(2026, 8, 22, 15, minute),
    )


class EntriesPayloadTests(unittest.TestCase):
    def test_shows_the_newest_entry_first(self):
        payload = entries_payload([annotation(quote="older", minute=1), annotation(quote="newer", minute=2)])

        self.assertEqual([entry["quote"] for entry in payload], ["newer", "older"])

    def test_carries_the_timestamp_the_interface_displays(self):
        payload = entries_payload([annotation()])

        self.assertEqual(payload[0]["stamp"], "2026-08-22 15:01")
        self.assertEqual(payload[0]["source"], "Firefox")


class AnnotationsFromPayloadTests(unittest.TestCase):
    def test_round_trips_the_list_back_into_file_order(self):
        original = [annotation(quote="older", minute=1), annotation(quote="newer", minute=2)]

        restored = annotations_from_payload(entries_payload(original))

        self.assertEqual(restored, original)

    def test_keeps_an_edited_quote_and_comment(self):
        payload = entries_payload([annotation()])
        payload[0]["quote"] = "  edited quote  "
        payload[0]["comment"] = "edited comment"

        restored = annotations_from_payload(payload)

        self.assertEqual(restored[0].quote, "edited quote")
        self.assertEqual(restored[0].comment, "edited comment")

    def test_refuses_an_entry_that_lost_its_comment(self):
        payload = entries_payload([annotation()])
        payload[0]["comment"] = "   "

        with self.assertRaises(ValueError):
            annotations_from_payload(payload)

    def test_a_removed_entry_stays_removed(self):
        payload = entries_payload([annotation(quote="keep", minute=1), annotation(quote="drop", minute=2)])

        restored = annotations_from_payload([entry for entry in payload if entry["quote"] != "drop"])

        self.assertEqual([item.quote for item in restored], ["keep"])


class BuildStateTests(unittest.TestCase):
    def test_offers_every_captured_candidate(self):
        state = build_state(
            candidates=[TextCandidate("Selected text", "one"), TextCandidate("Clipboard", "two")],
            source="Firefox",
            annotations=[],
            now=datetime(2026, 8, 22, 15, 20),
        )

        self.assertEqual(
            state["candidates"],
            [
                {"label": "Selected text", "text": "one"},
                {"label": "Clipboard", "text": "two"},
            ],
        )
        self.assertEqual(state["stamp"], "2026-08-22 15:20")
        self.assertEqual(state["source"], "Firefox")


class PageWithStateTests(unittest.TestCase):
    def test_hands_the_page_its_state_before_the_first_script_runs(self):
        page = page_with_state("<head></head><script>real()</script>", {"source": "Firefox"})

        self.assertLess(page.index("__STATE__"), page.index("real()"))
        self.assertIn('"source": "Firefox"', page)

    def test_a_quote_cannot_close_the_script_tag_early(self):
        page = page_with_state("<script>x</script>", {"source": "</script><script>evil()</script>"})

        self.assertNotIn("evil()</script>", page)
        self.assertIn("<\\/script>", page)

    def test_the_state_survives_as_valid_json(self):
        page = page_with_state("<script>x</script>", {"source": "Bad </script> window"})
        payload = page.split("window.__STATE__=", 1)[1].split(";</script>", 1)[0]

        self.assertEqual(json.loads(payload)["source"], "Bad </script> window")


class GuardedHostSaveTests(unittest.TestCase):
    def host(self, directory):
        host = AnnotatorWindow.__new__(AnnotatorWindow)
        host.directory = directory
        host.document = load_document(directory)
        host.saved_path = None
        host.messages = []
        host._to_page = host.messages.append
        return host

    def test_error_retains_loaded_baseline_and_never_reloads_entries(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path = directory / "annotations.md"
            path.write_text(render_annotation(annotation()))
            host = self.host(directory)
            baseline = host.document
            external = render_annotation(annotation(comment="External note"))
            path.write_text(external)
            draft = entries_payload([annotation(comment="My draft")])
            host._do_save({"entries": draft})
            self.assertIs(host.document, baseline)
            self.assertIsNone(host.saved_path)
            self.assertEqual([message["kind"] for message in host.messages], ["error"])
            self.assertIn("changed", host.messages[0]["status"])
            self.assertEqual(path.read_text(), external)
            self.assertEqual(draft[0]["comment"], "My draft")

    def test_success_uses_returned_baseline_and_supports_repeated_save(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            host = self.host(directory)
            with patch("desktop_annotator.webview.load_document", side_effect=AssertionError("Must not reload after save")):
                host._do_save({"entries": entries_payload([annotation(comment="First")])})
                self.assertEqual(host.document.raw_bytes, host.saved_path.read_bytes())
                host._do_save({"entries": entries_payload([annotation(comment="Second")])})
            self.assertEqual(host.document.entries[0].comment, "Second")
            self.assertEqual(host.messages[-1]["saveProblem"], "")
            self.assertEqual(host.messages[-1]["kind"], "entries")

    def test_reload_reports_diagnostics_alongside_usable_entries(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            host = self.host(directory)
            (directory / "annotations.md").write_text("Manual preamble\n" + render_annotation(annotation()))
            host._reload_entries("Reloaded")
            self.assertTrue(host.messages[-1]["saveProblem"])
            self.assertEqual(host.messages[-1]["entries"][0]["quote"], "quoted")

    def test_initial_state_reports_blocked_save(self):
        state = build_state(candidates=[], source="Firefox", annotations=[annotation()], save_problem="Unsafe input")
        self.assertEqual(state["saveProblem"], "Unsafe input")
        self.assertEqual(len(state["entries"]), 1)

    def test_invalid_legacy_utf8_startup_shows_a_load_diagnostic(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            legacy = directory / "2026-08-22.md"
            legacy.write_bytes(b"\xff legacy annotation")
            webkit = Mock()

            host = AnnotatorWindow(
                candidates=[], source="Firefox", directory=directory,
                gtk=Mock(), gdk=Mock(), webkit=webkit, glib=Mock(),
            )

            self.assertIn("Could not load annotations", host.document.save_problem)
            self.assertFalse(host.document.entries)
            self.assertIn("Could not load annotations", host.view.load_html.call_args.args[0])
            self.assertEqual(legacy.read_bytes(), b"\xff legacy annotation")
            self.assertFalse((directory / "annotations.md").exists())

    def test_reload_error_keeps_loaded_baseline_and_draft(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            host = self.host(directory)
            baseline = host.document
            legacy = directory / "2026-08-22.md"
            legacy.write_bytes(b"\xff legacy annotation")

            host._reload_entries("Reloaded")

            self.assertIs(host.document, baseline)
            self.assertEqual([message["kind"] for message in host.messages], ["error"])
            self.assertIn("decode", host.messages[0]["status"])
            self.assertEqual(legacy.read_bytes(), b"\xff legacy annotation")
            self.assertFalse((directory / "annotations.md").exists())

    def test_sublime_keeps_unsaved_draft_open_without_attempting_a_save(self):
        for scenario in ("unsaved", "unsafe", "conflicting"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as name:
                directory = Path(name)
                path = directory / "annotations.md"
                original = render_annotation(annotation())
                if scenario == "unsafe":
                    original = "Manual preamble\n" + original
                path.write_text(original)
                host = self.host(directory)
                baseline = host.document
                if scenario == "conflicting":
                    path.write_text(render_annotation(annotation(comment="External edit")))
                original_bytes = path.read_bytes()
                host.window = Mock()
                draft = entries_payload([annotation(comment="Unsaved draft")])

                with patch("desktop_annotator.webview._launch_sublime") as launch, patch("desktop_annotator.webview.save_edited_annotations", side_effect=AssertionError("Must not save")):
                    host._do_sublime({"entries": draft})

                launch.assert_called_once_with(path)
                host.window.close.assert_not_called()
                self.assertEqual(host.messages, [])
                self.assertIs(host.document, baseline)
                self.assertIsNone(host.saved_path)
                self.assertEqual(path.read_bytes(), original_bytes)
                self.assertEqual(draft[0]["comment"], "Unsaved draft")

    def test_migration_conflict_during_reload_keeps_loaded_baseline(self):
        with tempfile.TemporaryDirectory() as name:
            host = self.host(Path(name))
            baseline = host.document
            with patch("desktop_annotator.webview.load_document", side_effect=ValueError("Migration conflict")):
                host._reload_entries("Reloaded")
            self.assertIs(host.document, baseline)
            self.assertEqual(host.messages, [{"kind": "error", "pane": "list", "status": "Migration conflict"}])


if __name__ == "__main__":
    unittest.main()
