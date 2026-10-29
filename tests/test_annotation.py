import tempfile
import fcntl
import threading
import unittest
from unittest.mock import patch
from datetime import datetime
from pathlib import Path

from desktop_annotator.annotation import (
    Annotation,
    append_annotation,
    copyable_annotation_list,
    load_annotation_list,
    load_document,
    parse_annotation_list,
    parse_editable_body,
    render_annotation,
    render_annotation_list,
    render_editable_body,
    save_annotation_list,
)


class RenderAnnotationTests(unittest.TestCase):
    def test_renders_multiline_quote_and_comment_as_markdown(self):
        annotation = Annotation(
            quote="First selected line\nSecond selected line",
            comment="Explain the exception here.",
            source="Firefox — Agent response",
            captured_at=datetime(2026, 8, 20, 16, 42),
        )

        self.assertEqual(
            render_annotation(annotation),
            "## 2026-08-20 16:42 · Firefox — Agent response\n\n"
            "> First selected line\n"
            "> Second selected line\n\n"
            "→ Explain the exception here.\n",
        )

    def test_renders_blank_quote_lines_as_markdown_blockquote_lines(self):
        annotation = Annotation(
            quote="Before\n\nAfter",
            comment="Keep the paragraph break.",
            source="Text Editor",
            captured_at=datetime(2026, 8, 20, 9, 5),
        )

        rendered = render_annotation(annotation)

        self.assertIn("> Before\n>\n> After", rendered)


class AppendAnnotationTests(unittest.TestCase):
    def test_appends_multiple_entries_to_one_continuous_file(self):
        first = Annotation(
            quote="One",
            comment="First note",
            source="Window A",
            captured_at=datetime(2026, 8, 20, 10, 0),
        )
        second = Annotation(
            quote="Two",
            comment="Second note",
            source="Window B",
            captured_at=datetime(2026, 8, 20, 10, 1),
        )

        with tempfile.TemporaryDirectory() as directory:
            path = append_annotation(first, Path(directory))
            append_annotation(second, Path(directory))

            self.assertEqual(path.name, "annotations.md")
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                render_annotation(first) + "\n" + render_annotation(second) + "\n",
            )


class EditableAnnotationListTests(unittest.TestCase):
    def test_first_load_copies_daily_files_into_the_continuous_list(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            old_file = directory / "2026-08-19.md"
            new_file = directory / "2026-08-20.md"
            old_file.write_text("## 09:00 · Old window\n\n> Old quote\n\n→ Old note\n", encoding="utf-8")
            new_file.write_text("## 10:00 · New window\n\n> New quote\n\n→ New note\n", encoding="utf-8")

            text = load_annotation_list(directory)

            self.assertIn("## 2026-08-19 09:00 · Old window", text)
            self.assertIn("→ Old note", text)
            self.assertIn("## 2026-08-20 10:00 · New window", text)
            self.assertIn("→ New note", text)
            self.assertEqual(old_file.read_text(encoding="utf-8").splitlines()[-1], "→ Old note")
            self.assertEqual(new_file.read_text(encoding="utf-8").splitlines()[-1], "→ New note")
            self.assertEqual((directory / "annotations.md").read_text(encoding="utf-8"), text)

    def test_user_can_replace_the_editable_list_contents(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)

            document = save_annotation_list(directory, "Edited continuous list\n", expected=load_document(directory))
            path = document.path

            self.assertEqual(path.name, "annotations.md")
            self.assertEqual(load_annotation_list(directory), "Edited continuous list\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class StructuredAnnotationListTests(unittest.TestCase):
    def test_round_trips_entries_for_structured_editing(self):
        entries = [
            Annotation(
                quote="First line\nSecond line",
                comment="Editable comment",
                source="Firefox",
                captured_at=datetime(2026, 8, 20, 18, 4),
            ),
            Annotation(
                quote="Another quote",
                comment="Another comment",
                source="Clipboard · Terminal",
                captured_at=datetime(2026, 8, 20, 18, 5),
            ),
        ]

        parsed = parse_annotation_list(render_annotation_list(entries))

        self.assertEqual(parsed, entries)

    def test_copyable_list_omits_timestamps_and_sources(self):
        entries = [
            Annotation(
                quote="Selected phrase",
                comment="Change this.",
                source="Clipboard · Firefox",
                captured_at=datetime(2026, 8, 20, 18, 4),
            )
        ]

        copied = copyable_annotation_list(entries)

        self.assertEqual(copied, "> Selected phrase\n\n→ Change this.\n")
        self.assertNotIn("2026", copied)
        self.assertNotIn("Firefox", copied)

    def test_editable_body_has_no_timestamp_or_source_text(self):
        entry = Annotation(
            quote="First line\nSecond line",
            comment="Editable comment",
            source="Firefox",
            captured_at=datetime(2026, 8, 20, 18, 4),
        )

        body = render_editable_body(entry)

        self.assertEqual(body, "> First line\n> Second line\n\n→ Editable comment\n")
        self.assertNotIn("2026", body)
        self.assertNotIn("Firefox", body)

    def test_parses_one_long_editor_body_without_changing_metadata(self):
        original = Annotation(
            quote="Old quote",
            comment="Old comment",
            source="Clipboard · Firefox",
            captured_at=datetime(2026, 8, 20, 18, 4),
        )

        edited = parse_editable_body(
            original,
            "> Edited first line\n> Edited second line\n\n→ Edited comment\ncontinued",
        )

        self.assertEqual(edited.quote, "Edited first line\nEdited second line")
        self.assertEqual(edited.comment, "Edited comment\ncontinued")
        self.assertEqual(edited.source, original.source)
        self.assertEqual(edited.captured_at, original.captured_at)


class DocumentSafetyTests(unittest.TestCase):
    def entry(self, comment="A note"):
        return Annotation("A quote", comment, "Firefox", datetime(2026, 8, 20, 18, 4))

    def test_missing_file_and_empty_file_have_distinct_snapshots(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            missing = load_document(directory)
            missing.path.write_bytes(b"")
            empty = load_document(directory)
            self.assertIsNone(missing.raw_bytes)
            self.assertEqual(empty.raw_bytes, b"")
            self.assertFalse(empty.problems)

    def test_load_keeps_valid_entries_and_diagnoses_every_skipped_entry(self):
        good = render_annotation(self.entry())
        cases = {
            "preamble": ("Personal introduction\n" + good, 1),
            "bad date": (good + good.replace("2026-08-20", "2026-99-20"), 1),
            "bad body": (good + "## 2026-08-20 18:05 · Broken\n\nMissing markup\n", 1),
            "empty quote": (good + good.replace("> A quote", ">"), 1),
            "empty comment": (good + good.replace("→ A note", "→"), 1),
            "only foreign text": ("Do not destroy this file.\n", 0),
        }
        for label, (text, count) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as name:
                directory = Path(name)
                path = directory / "annotations.md"
                raw_bytes = text.encode()
                path.write_bytes(raw_bytes)
                document = load_document(directory)
                self.assertEqual(len(document.entries), count)
                self.assertTrue(document.problems)
                with self.assertRaises(ValueError):
                    save_annotation_list(directory, good, expected=document)
                self.assertEqual(path.read_bytes(), raw_bytes)

    def test_invalid_date_does_not_crash_the_permissive_parser(self):
        valid = render_annotation(self.entry())
        self.assertEqual(parse_annotation_list(valid.replace("2026-08-20", "2026-99-20") + valid), [self.entry()])

    def test_invalid_utf8_is_diagnosed_and_append_preserves_original_bytes(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path = directory / "annotations.md"
            original = b"Unreadable byte: \xff"
            path.write_bytes(original)
            document = load_document(directory)
            self.assertEqual(document.raw_bytes, original)
            self.assertTrue(document.problems)
            append_annotation(self.entry(), directory)
            self.assertTrue(path.read_bytes().startswith(original + b"\n\n"))
            self.assertIn(render_annotation(self.entry()).encode(), path.read_bytes())

    def test_whitespace_preamble_is_safe(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            (directory / "annotations.md").write_text("\n  \n" + render_annotation(self.entry()))
            self.assertFalse(load_document(directory).problems)

    def test_changed_created_and_deleted_files_are_never_overwritten(self):
        for change in ("changed", "created", "deleted"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as name:
                directory = Path(name)
                path = directory / "annotations.md"
                if change != "created":
                    path.write_text(render_annotation(self.entry()))
                document = load_document(directory)
                if change == "deleted":
                    path.unlink()
                    external = None
                else:
                    external = render_annotation(self.entry("External edit")).encode()
                    path.write_bytes(external)
                with self.assertRaisesRegex(ValueError, "changed"):
                    save_annotation_list(directory, "", expected=document)
                self.assertEqual(path.read_bytes() if path.exists() else None, external)

    def test_save_returns_exact_baseline_bytes_for_a_second_save(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            document = save_annotation_list(directory, render_annotation(self.entry()), expected=load_document(directory))
            self.assertEqual(document.raw_bytes, document.path.read_bytes())
            second = save_annotation_list(directory, "", expected=document)
            self.assertEqual(second.raw_bytes, b"")
            self.assertEqual(second.entries, ())

    def test_failure_before_replacement_cleans_up_and_preserves_original(self):
        for target in ("_write_all", "os.fsync", "os.replace"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as name:
                directory = Path(name)
                path = directory / "annotations.md"
                original = render_annotation(self.entry()).encode()
                path.write_bytes(original)
                document = load_document(directory)
                with patch("desktop_annotator.annotation." + target, side_effect=OSError("simulated failure")):
                    with self.assertRaisesRegex(OSError, "simulated failure"):
                        save_annotation_list(directory, "", expected=document)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(list(directory.glob(".annotations.md.*.tmp")), [])

    def test_external_change_during_temporary_write_is_detected_before_replace(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path = directory / "annotations.md"
            original = render_annotation(self.entry()).encode()
            external = render_annotation(self.entry("Changed during save")).encode()
            path.write_bytes(original)
            document = load_document(directory)
            from desktop_annotator.annotation import _write_all
            def intervening_write(descriptor, payload):
                _write_all(descriptor, payload)
                path.write_bytes(external)
            with patch("desktop_annotator.annotation._write_all", side_effect=intervening_write):
                with self.assertRaisesRegex(ValueError, "changed"):
                    save_annotation_list(directory, "", expected=document)
            self.assertEqual(path.read_bytes(), external)
            self.assertEqual(list(directory.glob(".annotations.md.*.tmp")), [])

    def test_append_waits_for_the_stable_document_lock_and_invalidates_old_draft(self):
        from desktop_annotator.annotation import _document_lock
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path = directory / "annotations.md"
            original = render_annotation(self.entry()).encode()
            path.write_bytes(original)
            document = load_document(directory)
            attempted, finished = threading.Event(), threading.Event()
            errors = []
            original_flock = fcntl.flock
            def record_flock(descriptor, operation):
                attempted.set()
                original_flock(descriptor, operation)
            def append():
                try:
                    append_annotation(self.entry("Concurrent add"), directory)
                except Exception as error:
                    errors.append(error)
                finally:
                    finished.set()
            with _document_lock(directory):
                with patch("desktop_annotator.annotation.fcntl.flock", side_effect=record_flock):
                    worker = threading.Thread(target=append, daemon=True)
                    worker.start()
                    self.assertTrue(attempted.wait(2))
                    self.assertFalse(finished.is_set())
                    self.assertEqual(path.read_bytes(), original)
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors)
            self.assertIn(b"Concurrent add", path.read_bytes())
            with self.assertRaisesRegex(ValueError, "changed"):
                save_annotation_list(directory, "", expected=document)

    def test_legacy_stale_temp_filename_cannot_block_a_save(self):
        import os
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            stale = directory / f".annotations.md.{os.getpid()}.tmp"
            stale.write_text("left over from a crashed process")
            document = save_annotation_list(directory, render_annotation(self.entry()), expected=load_document(directory))
            self.assertEqual(document.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(stale.read_text(), "left over from a crashed process")


if __name__ == "__main__":
    unittest.main()
