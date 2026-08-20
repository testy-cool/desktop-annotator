import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from desktop_annotator.annotation import (
    Annotation,
    append_annotation,
    copyable_annotation_list,
    load_annotation_list,
    parse_annotation_list,
    render_annotation,
    render_annotation_list,
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

            path = save_annotation_list(directory, "Edited continuous list\n")

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


if __name__ == "__main__":
    unittest.main()
