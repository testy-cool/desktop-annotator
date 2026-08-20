from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ANNOTATION_LIST_NAME = "annotations.md"
DAILY_ANNOTATION_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
ENTRY_HEADER = re.compile(
    r"^## (?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}) · (?P<source>.+)$",
    re.MULTILINE,
)


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
        f"## {annotation.captured_at:%Y-%m-%d %H:%M} · {annotation.source}\n\n"
        f"{quote}\n\n"
        f"→ {annotation.comment}\n"
    )


def render_annotation_list(annotations: list[Annotation]) -> str:
    return "\n".join(render_annotation(annotation) for annotation in annotations)


def parse_annotation_list(text: str) -> list[Annotation]:
    matches = list(ENTRY_HEADER.finditer(text))
    annotations = []
    for index, match in enumerate(matches):
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body_lines = text[match.end() : body_end].strip().splitlines()

        quote_lines = []
        position = 0
        while position < len(body_lines) and body_lines[position].startswith(">"):
            line = body_lines[position]
            quote_lines.append(line[2:] if line.startswith("> ") else line[1:])
            position += 1

        while position < len(body_lines) and not body_lines[position].strip():
            position += 1
        if not quote_lines or position >= len(body_lines) or not body_lines[position].startswith("→"):
            continue

        first_comment_line = body_lines[position][1:].lstrip()
        comment_lines = [first_comment_line, *body_lines[position + 1 :]]
        annotations.append(
            Annotation(
                quote="\n".join(quote_lines),
                comment="\n".join(comment_lines).rstrip(),
                source=match.group("source"),
                captured_at=datetime.strptime(match.group("timestamp"), "%Y-%m-%d %H:%M"),
            )
        )
    return annotations


def copyable_annotation_list(annotations: list[Annotation]) -> str:
    entries = []
    for annotation in annotations:
        quote_lines = [f"> {line}" if line else ">" for line in annotation.quote.splitlines()]
        entries.append(f"{'\n'.join(quote_lines)}\n\n→ {annotation.comment}\n")
    return "\n".join(entries)


def render_editable_body(annotation: Annotation) -> str:
    return copyable_annotation_list([annotation])


def parse_editable_body(original: Annotation, text: str) -> Annotation:
    document = (
        f"## {original.captured_at:%Y-%m-%d %H:%M} · {original.source}\n\n"
        f"{text.strip()}\n"
    )
    parsed = parse_annotation_list(document)
    if len(parsed) != 1:
        raise ValueError("entry must contain a quoted passage and comment")
    return parsed[0]


def _ensure_directory(directory: Path) -> None:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)


def _write_all(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        remaining = remaining[written:]


def _create_continuous_list_from_daily_files(directory: Path) -> Path | None:
    daily_files = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and DAILY_ANNOTATION_NAME.fullmatch(path.name)
    )
    if not daily_files:
        return None

    chunks = []
    for path in daily_files:
        content = path.read_text(encoding="utf-8").rstrip()
        date = path.stem
        content = re.sub(
            r"(?m)^## (\d{2}:\d{2}) ·",
            lambda match: f"## {date} {match.group(1)} ·",
            content,
        )
        chunks.append(f"{content}\n")
    payload = ("\n".join(chunks).rstrip() + "\n").encode("utf-8")

    target = directory / ANNOTATION_LIST_NAME
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return target
    try:
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return target


def load_annotation_list(directory: Path) -> str:
    _ensure_directory(directory)
    path = directory / ANNOTATION_LIST_NAME
    if not path.exists():
        _create_continuous_list_from_daily_files(directory)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def save_annotation_list(directory: Path, text: str) -> Path:
    _ensure_directory(directory)
    path = directory / ANNOTATION_LIST_NAME
    temporary = directory / f".{ANNOTATION_LIST_NAME}.{os.getpid()}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        _write_all(descriptor, text.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    return path


def append_annotation(annotation: Annotation, directory: Path) -> Path:
    load_annotation_list(directory)
    path = directory / ANNOTATION_LIST_NAME
    payload = (render_annotation(annotation) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        _write_all(descriptor, payload)
    finally:
        os.close(descriptor)
    return path
