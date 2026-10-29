from __future__ import annotations

import fcntl
import os
import re
import tempfile
from contextlib import contextmanager
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


@dataclass(frozen=True)
class DocumentSnapshot:
    path: Path
    raw_bytes: bytes | None
    entries: tuple[Annotation, ...]
    problems: tuple[str, ...]

    @property
    def save_problem(self) -> str:
        return " ".join(self.problems)


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


def _parse_document(text: str) -> tuple[tuple[Annotation, ...], tuple[str, ...]]:
    matches = list(ENTRY_HEADER.finditer(text))
    annotations = []
    problems = []
    preamble_end = matches[0].start() if matches else len(text)
    if text[:preamble_end].strip():
        problems.append("The file contains text outside recognized entries; list saving is disabled.")
    for index, match in enumerate(matches):
        label = f"Entry {index + 1}"
        try:
            captured_at = datetime.strptime(match.group("timestamp"), "%Y-%m-%d %H:%M")
        except ValueError:
            problems.append(f"{label} has an invalid date and could not be loaded.")
            continue
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
            problems.append(f"{label} could not be loaded: a quote and comment are required.")
            continue
        quote = "\n".join(quote_lines)
        comment = "\n".join([body_lines[position][1:].lstrip(), *body_lines[position + 1 :]]).rstrip()
        if not quote.strip() or not comment.strip():
            problems.append(f"{label} has an empty quote or comment and could not be loaded.")
            continue
        annotations.append(Annotation(quote, comment, match.group("source"), captured_at))
    return tuple(annotations), tuple(problems)


def parse_annotation_list(text: str) -> list[Annotation]:
    """Read usable entries, leaving diagnostics to load_document."""
    return list(_parse_document(text)[0])


def copyable_annotation_list(annotations: list[Annotation]) -> str:
    entries = []
    for annotation in annotations:
        quote_lines = [f"> {line}" if line else ">" for line in annotation.quote.splitlines()]
        quote = "\n".join(quote_lines)
        entries.append(f"{quote}\n\n→ {annotation.comment}\n")
    return "\n".join(entries)


def render_editable_body(annotation: Annotation) -> str:
    return copyable_annotation_list([annotation])


def parse_editable_body(original: Annotation, text: str) -> Annotation:
    document = (
        f"## {original.captured_at:%Y-%m-%d %H:%M} · {original.source}\n\n"
        f"{text.strip()}\n"
    )
    parsed, problems = _parse_document(document)
    if problems or len(parsed) != 1:
        raise ValueError("entry must contain one quoted passage and comment")
    return parsed[0]


def _ensure_directory(directory: Path) -> None:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)


@contextmanager
def _document_lock(directory: Path):
    """Lock a stable sidecar, since replacing the document changes its inode."""
    _ensure_directory(directory)
    descriptor = os.open(directory / ".annotations.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("Could not finish writing annotations")
        remaining = remaining[written:]


def _replace_document(path: Path, payload: bytes, *, expected_bytes: bytes | None) -> None:
    descriptor, name = tempfile.mkstemp(prefix=f".{ANNOTATION_LIST_NAME}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        try:
            _write_all(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if _read_bytes(path) != expected_bytes:
            raise ValueError("The annotation file changed since it was loaded. Copy your draft before reloading.")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _create_continuous_list_from_daily_files(directory: Path) -> Path | None:
    """Called only while holding the document lock."""
    daily_files = sorted(
        path for path in directory.iterdir()
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
    _replace_document(target, payload, expected_bytes=None)
    return target


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _snapshot(path: Path, raw_bytes: bytes | None) -> DocumentSnapshot:
    if raw_bytes is None:
        return DocumentSnapshot(path, None, (), ())
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("utf-8", errors="replace")
        entries, problems = _parse_document(text)
        return DocumentSnapshot(path, raw_bytes, entries, ("The file is not valid UTF-8; list saving is disabled.", *problems))
    entries, problems = _parse_document(text)
    return DocumentSnapshot(path, raw_bytes, entries, problems)


def load_document(directory: Path) -> DocumentSnapshot:
    with _document_lock(directory):
        path = directory / ANNOTATION_LIST_NAME
        raw_bytes = _read_bytes(path)
        if raw_bytes is None:
            _create_continuous_list_from_daily_files(directory)
            raw_bytes = _read_bytes(path)
        return _snapshot(path, raw_bytes)


def load_annotation_list(directory: Path) -> str:
    document = load_document(directory)
    return (document.raw_bytes or b"").decode("utf-8")


def save_annotation_list(directory: Path, text: str, *, expected: DocumentSnapshot) -> DocumentSnapshot:
    """Replace only the fully readable document the editor actually loaded."""
    with _document_lock(directory):
        path = directory / ANNOTATION_LIST_NAME
        if path.absolute() != expected.path.absolute():
            raise ValueError("This draft belongs to a different annotation file.")
        if expected.problems:
            raise ValueError("Cannot save this list safely. " + expected.save_problem + " Copy your draft or open the file in Sublime.")
        if _read_bytes(path) != expected.raw_bytes:
            raise ValueError("The annotation file changed since it was loaded. Copy your draft before reloading.")
        # Check the original bytes too, rather than trusting caller-supplied diagnostics.
        if _snapshot(path, expected.raw_bytes).problems:
            raise ValueError("The original annotation file cannot be safely replaced.")
        payload = text.encode("utf-8")
        snapshot = _snapshot(path, payload)
        _replace_document(path, payload, expected_bytes=expected.raw_bytes)
        return snapshot


def append_annotation(annotation: Annotation, directory: Path) -> Path:
    with _document_lock(directory):
        path = directory / ANNOTATION_LIST_NAME
        raw_bytes = _read_bytes(path)
        if raw_bytes is None:
            _create_continuous_list_from_daily_files(directory)
            raw_bytes = _read_bytes(path)
        separator = b"" if not raw_bytes or raw_bytes.endswith(b"\n\n") else b"\n" if raw_bytes.endswith(b"\n") else b"\n\n"
        payload = separator + (render_annotation(annotation) + "\n").encode("utf-8")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            _write_all(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return path
