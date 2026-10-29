import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_annotator.settings import load_layout, save_layout


class LayoutSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config_home = Path(temporary.name)
        environment = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config_home)})
        environment.start()
        self.addCleanup(environment.stop)
        self.path = self.config_home / "desktop-annotator" / "settings.json"

    def write_settings(self, text):
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(text)

    def test_missing_preferences_default_to_tabs_without_creating_files(self):
        self.assertEqual(load_layout(), "tabs")
        self.assertFalse(self.path.parent.exists())

    def test_saved_layout_survives_a_new_read_and_preserves_other_keys(self):
        self.write_settings('{"layout":"tabs","other":{"enabled":true}}')
        save_layout("split")
        self.assertEqual(load_layout(), "split")
        self.assertEqual(json.loads(self.path.read_text())["other"], {"enabled": True})
        save_layout("tabs")
        self.assertEqual(load_layout(), "tabs")

    def test_malformed_preferences_and_unknown_layouts_default_to_tabs(self):
        for text in ("broken", "[]", "null", '"split"', '{"layout":"wide"}', '{"layout":[]}', '{"layout":true}'):
            with self.subTest(text=text):
                self.write_settings(text)
                self.assertEqual(load_layout(), "tabs")
        self.path.write_bytes(b"\xff")
        self.assertEqual(load_layout(), "tabs")

    def test_saving_replaces_malformed_preferences(self):
        self.write_settings("broken")
        save_layout("split")
        self.assertEqual(json.loads(self.path.read_text()), {"layout": "split"})

    def test_invalid_layout_never_touches_saved_preferences(self):
        self.write_settings('{"layout":"split"}')
        original = self.path.read_bytes()
        for layout in (None, "", "Split", "wide", True, [], {}):
            with self.subTest(layout=layout), self.assertRaises(ValueError):
                save_layout(layout)
        self.assertEqual(self.path.read_bytes(), original)

    def test_new_settings_directory_and_replacement_file_are_private(self):
        save_layout("split")
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.path.chmod(0o644)
        save_layout("tabs")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_failed_replace_preserves_original_and_removes_temporary_file(self):
        self.write_settings('{"layout":"tabs","other":1}')
        original = self.path.read_bytes()
        with patch("desktop_annotator.settings.os.replace", side_effect=OSError("Disk unavailable")):
            with self.assertRaises(OSError):
                save_layout("split")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_failed_write_cleans_up_temporary_file(self):
        with patch("desktop_annotator.settings.json.dump", side_effect=OSError("Disk full")):
            with self.assertRaises(OSError):
                save_layout("split")
        self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_unreadable_preferences_default_to_tabs_but_save_reports_the_failure(self):
        with patch("desktop_annotator.settings.Path.read_text", side_effect=PermissionError("Denied")):
            self.assertEqual(load_layout(), "tabs")
            with self.assertRaises(PermissionError):
                save_layout("split")
        self.assertFalse(self.path.parent.exists())

    def test_unset_or_empty_xdg_config_home_uses_home_config(self):
        for setting in (None, ""):
            with self.subTest(setting=setting), patch("desktop_annotator.settings.Path.home", return_value=self.config_home):
                with patch.dict(os.environ):
                    if setting is None:
                        os.environ.pop("XDG_CONFIG_HOME", None)
                    else:
                        os.environ["XDG_CONFIG_HOME"] = setting
                    save_layout("split")
                    self.assertEqual(load_layout(), "split")
        self.assertTrue((self.config_home / ".config" / "desktop-annotator" / "settings.json").exists())


if __name__ == "__main__":
    unittest.main()
