import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from desktop_annotator.workflow import save_comment


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


if __name__ == "__main__":
    unittest.main()
