from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Annotation:
    quote: str
    comment: str
    source: str
    captured_at: datetime


def render_annotation(annotation: Annotation) -> str:
    quote_lines = [f"> {line}" if line else ">" for line in annotation.quote.splitlines()]
    quote = "\n".join(quote_lines)
    return (
        f"## {annotation.captured_at:%H:%M} · {annotation.source}\n\n"
        f"{quote}\n\n"
        f"→ {annotation.comment}\n"
    )


def append_annotation(annotation: Annotation, directory: Path) -> Path:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / f"{annotation.captured_at:%Y-%m-%d}.md"
    payload = (render_annotation(annotation) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)
    return path
