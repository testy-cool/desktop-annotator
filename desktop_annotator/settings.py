"""Small, private preferences shared by annotator launches."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def _settings_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    return base / "desktop-annotator" / "settings.json"


def _read_settings(path: Path) -> dict:
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, UnicodeError):
        return {}
    return settings if isinstance(settings, dict) else {}


def load_layout() -> str:
    """Use tabs until the user explicitly saves a supported layout."""
    try:
        layout = _read_settings(_settings_path()).get("layout")
    except OSError:
        return "tabs"
    return layout if layout in ("tabs", "split") else "tabs"


def save_layout(layout: str) -> None:
    """Atomically replace the preference, retaining other settings keys."""
    if layout not in ("tabs", "split"):
        raise ValueError("Layout must be tabs or split.")
    path = _settings_path()
    settings = _read_settings(path)
    settings["layout"] = layout
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".settings.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(settings, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
