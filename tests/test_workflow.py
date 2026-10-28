import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from desktop_annotator.annotation import Annotation, load_annotation_list, load_document, parse_annotation_list, render_annotation
from desktop_annotator.workflow import (
    annotation_source,
    save_comment,
    save_edited_annotations,
    update_annotation,
)


class SaveCommentTests(unittest.TestCase):
    def test_saves_trimmed_input_and_returns_the_written_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_comment(
                quote="  selected phrase  ",
                comment="  Make this more direct.  ",
                source="  Firefox — answer  ",
                directory=Path(directory),
                captured_at=datetime(2026, 8, 20, 17, 10),
            )

            self.assertEqual(path.name, "annotations.md")
            self.assertIn("> selected phrase", path.read_text(encoding="utf-8"))
            self.assertIn("→ Make this more direct.", path.read_text(encoding="utf-8"))

    def test_rejects_an_empty_comment(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "comment"):
                save_comment(
                    quote="selected phrase",
                    comment="   ",
                    source="Firefox",
                    directory=Path(directory),
                )


class EditableListWorkflowTests(unittest.TestCase):
    def test_clipboard_source_is_identified_without_changing_selection_source(self):
        self.assertEqual(annotation_source("Selected text", "Firefox"), "Firefox")
        self.assertEqual(annotation_source("Clipboard", "Firefox"), "Clipboard · Firefox")

    def test_editing_preserves_noneditable_timestamp_and_source(self):
        original = Annotation(
            quote="Original quote",
            comment="Original comment",
            source="Firefox",
            captured_at=datetime(2026, 8, 20, 18, 20),
        )

        edited = update_annotation(original, quote=" Edited quote ", comment=" Edited comment ")

        self.assertEqual(edited.quote, "Edited quote")
        self.assertEqual(edited.comment, "Edited comment")
        self.assertEqual(edited.source, original.source)
        self.assertEqual(edited.captured_at, original.captured_at)

    def test_saves_all_edited_entries_back_to_the_continuous_file(self):
        entry = Annotation(
            quote="Edited quote",
            comment="Edited comment",
            source="Firefox",
            captured_at=datetime(2026, 8, 20, 18, 20),
        )
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)

            document = save_edited_annotations([entry], directory, expected=load_document(directory))

            self.assertEqual(document.path.name, "annotations.md")
            self.assertEqual(parse_annotation_list(load_annotation_list(directory)), [entry])

    def test_ambiguous_comment_header_cannot_silently_split_or_drop_an_entry(self):
        entry = Annotation(
            quote="Edited quote",
            comment="Keep this\n## 2026-08-20 18:21 · Looks like metadata\n\n> Nested quote\n\n→ Nested comment",
            source="Firefox", captured_at=datetime(2026, 8, 20, 18, 20),
        )
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            original = Annotation("Original quote", "Original note", "Firefox", entry.captured_at)
            path = directory / "annotations.md"
            path.write_text(render_annotation(original))
            document = load_document(directory)
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "represented safely"):
                save_edited_annotations([entry], directory, expected=document)
            self.assertEqual(path.read_bytes(), before)

    def test_empty_edited_list_requires_a_safe_unchanged_original(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path = directory / "annotations.md"
            before = b"A manual note that cannot be parsed.\n"
            path.write_bytes(before)
            with self.assertRaises(ValueError):
                save_edited_annotations([], directory, expected=load_document(directory))
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
