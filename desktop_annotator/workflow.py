from __future__ import annotations

from datetime import datetime
from pathlib import Path

from desktop_annotator.annotation import (
    Annotation,
    append_annotation,
    render_annotation_list,
    save_annotation_list,
)


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


def annotation_source(candidate_label: str, active_window_title: str) -> str:
    if candidate_label == "Clipboard":
        return f"Clipboard · {active_window_title}"
    return active_window_title


def update_annotation(original: Annotation, *, quote: str, comment: str) -> Annotation:
    quote = quote.strip()
    comment = comment.strip()
    if not quote:
        raise ValueError("quote cannot be empty")
    if not comment:
        raise ValueError("comment cannot be empty")
    return Annotation(
        quote=quote,
        comment=comment,
        source=original.source,
        captured_at=original.captured_at,
    )


def save_edited_annotations(annotations: list[Annotation], directory: Path) -> Path:
    return save_annotation_list(directory, render_annotation_list(annotations))
