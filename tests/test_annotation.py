import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from desktop_annotator.annotation import Annotation, append_annotation, render_annotation


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
            "## 16:42 · Firefox — Agent response\n\n"
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
    def test_appends_multiple_entries_to_a_daily_file(self):
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

            self.assertEqual(path.name, "2026-08-20.md")
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                render_annotation(first) + "\n" + render_annotation(second) + "\n",
            )


if __name__ == "__main__":
    unittest.main()
