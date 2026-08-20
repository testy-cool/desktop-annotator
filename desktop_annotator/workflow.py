from __future__ import annotations

from datetime import datetime
from pathlib import Path

from desktop_annotator.annotation import Annotation, append_annotation


def save_comment(
    *,
    quote: str,
    comment: str,
    source: str,
    directory: Path,
    captured_at: datetime | None = None,
) -> Path:
    quote = quote.strip()
    comment = comment.strip()
    source = source.strip() or "Unknown window"
    if not quote:
        raise ValueError("quote cannot be empty")
    if not comment:
        raise ValueError("comment cannot be empty")

    return append_annotation(
        Annotation(
            quote=quote,
            comment=comment,
            source=source,
            captured_at=captured_at or datetime.now().astimezone(),
        ),
        directory,
    )
