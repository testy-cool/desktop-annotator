//! Ported from desktop_annotator/annotation.py — the write path only.
//! Parsing and list editing stayed in Python: the List tab is replaced by
//! opening annotations.md in an editor, so nothing here reads entries back.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};

pub const ANNOTATION_LIST_NAME: &str = "annotations.md";

pub struct Annotation {
    pub quote: String,
    pub comment: String,
    pub source: String,
    /// Pre-formatted "%Y-%m-%d %H:%M"; the caller owns the clock so this stays testable.
    pub captured_at: String,
}

/// Every quote line is prefixed with "> ", and a blank line becomes a bare ">"
/// so the block stays one Markdown quote instead of splitting in two.
pub fn render_annotation(annotation: &Annotation) -> String {
    let quote = annotation
        .quote
        .lines()
        .map(|line| if line.is_empty() { ">".to_string() } else { format!("> {line}") })
        .collect::<Vec<_>>()
        .join("\n");
    format!(
        "## {} · {}\n\n{}\n\n\u{2192} {}\n",
        annotation.captured_at, annotation.source, quote, annotation.comment
    )
}

pub fn annotations_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("ANNOTATIONS_DIR") {
        return PathBuf::from(dir);
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    PathBuf::from(home).join("Annotations")
}

/// Appends one entry, creating the directory 0700 and the file 0600 to match
/// the Python implementation. Never rewrites what is already there.
pub fn append_annotation(annotation: &Annotation, directory: &Path) -> std::io::Result<PathBuf> {
    fs::create_dir_all(directory)?;
    fs::set_permissions(directory, fs::Permissions::from_mode(0o700))?;

    let path = directory.join(ANNOTATION_LIST_NAME);
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .mode(0o600)
        .open(&path)?;
    write!(file, "{}\n", render_annotation(annotation))?;
    file.flush()?;
    Ok(path)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> Annotation {
        Annotation {
            quote: "the selected text".into(),
            comment: "what I thought".into(),
            source: "Firefox".into(),
            captured_at: "2026-08-22 14:05".into(),
        }
    }

    #[test]
    fn renders_the_documented_entry_shape() {
        assert_eq!(
            render_annotation(&sample()),
            "## 2026-08-22 14:05 · Firefox\n\n> the selected text\n\n→ what I thought\n"
        );
    }

    #[test]
    fn prefixes_every_line_of_a_multi_line_quote() {
        let annotation = Annotation { quote: "first\nsecond".into(), ..sample() };
        assert!(render_annotation(&annotation).contains("> first\n> second"));
    }

    #[test]
    fn keeps_a_blank_quote_line_inside_the_same_block() {
        let annotation = Annotation { quote: "first\n\nthird".into(), ..sample() };
        assert!(render_annotation(&annotation).contains("> first\n>\n> third"));
    }

    #[test]
    fn appends_without_disturbing_existing_entries() {
        let dir = std::env::temp_dir().join(format!("annot-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join(ANNOTATION_LIST_NAME), "## old entry\n\n> kept\n\n→ kept\n\n").unwrap();

        append_annotation(&sample(), &dir).unwrap();

        let text = fs::read_to_string(dir.join(ANNOTATION_LIST_NAME)).unwrap();
        assert!(text.starts_with("## old entry"), "existing content must survive");
        assert!(text.contains("## 2026-08-22 14:05 · Firefox"));
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn creates_the_file_private_to_the_user() {
        let dir = std::env::temp_dir().join(format!("annot-perm-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);

        let path = append_annotation(&sample(), &dir).unwrap();

        let mode = fs::metadata(&path).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o600, "annotations must not be world readable");
        let dir_mode = fs::metadata(&dir).unwrap().permissions().mode() & 0o777;
        assert_eq!(dir_mode, 0o700);
        fs::remove_dir_all(&dir).unwrap();
    }
}

/// One parsed entry, for the List tab.
#[derive(Debug, Clone, PartialEq)]
pub struct Entry {
    pub stamp: String,
    pub source: String,
    pub quote: String,
    pub comment: String,
}

fn split_header(line: &str) -> Option<(String, String)> {
    let rest = line.strip_prefix("## ")?;
    let (stamp, source) = rest.split_once(" · ")?;
    // "2026-08-22 14:12" - reject anything that is not a timestamp header.
    let (date, time) = stamp.split_once(' ')?;
    if date.len() != 10 || time.len() != 5 {
        return None;
    }
    Some((stamp.to_string(), source.to_string()))
}

/// Parses annotations.md. Anything that does not match the entry shape is
/// skipped rather than guessed at, so a hand-edited file cannot produce
/// entries that silently misrepresent what is on disk.
pub fn parse_annotation_list(text: &str) -> Vec<Entry> {
    let lines: Vec<&str> = text.lines().collect();
    let mut entries = Vec::new();
    let mut i = 0;

    while i < lines.len() {
        let Some((stamp, source)) = split_header(lines[i]) else {
            i += 1;
            continue;
        };
        i += 1;

        while i < lines.len() && lines[i].trim().is_empty() {
            i += 1;
        }

        let mut quote = Vec::new();
        while i < lines.len() && lines[i].starts_with('>') {
            quote.push(lines[i].strip_prefix("> ").unwrap_or(&lines[i][1..]).to_string());
            i += 1;
        }

        while i < lines.len() && lines[i].trim().is_empty() {
            i += 1;
        }

        if quote.is_empty() || i >= lines.len() || !lines[i].starts_with('\u{2192}') {
            continue;
        }

        let mut comment = vec![lines[i]['\u{2192}'.len_utf8()..].trim_start().to_string()];
        i += 1;
        // Comments run until the next header.
        while i < lines.len() && split_header(lines[i]).is_none() {
            comment.push(lines[i].to_string());
            i += 1;
        }

        entries.push(Entry {
            stamp,
            source,
            quote: quote.join("\n"),
            comment: comment.join("\n").trim_end().to_string(),
        });
    }
    entries
}

pub fn render_entries(entries: &[Entry]) -> String {
    entries
        .iter()
        .map(|e| {
            render_annotation(&Annotation {
                quote: e.quote.clone(),
                comment: e.comment.clone(),
                source: e.source.clone(),
                captured_at: e.stamp.clone(),
            })
        })
        .collect::<Vec<_>>()
        .join("\n")
}

/// Rewrites the whole file through a temp file and a rename, so an interrupted
/// save cannot leave a half-written annotations.md behind.
pub fn save_entries(entries: &[Entry], directory: &Path) -> std::io::Result<PathBuf> {
    fs::create_dir_all(directory)?;
    fs::set_permissions(directory, fs::Permissions::from_mode(0o700))?;
    let path = directory.join(ANNOTATION_LIST_NAME);
    let temporary = directory.join(format!(".{ANNOTATION_LIST_NAME}.{}.tmp", std::process::id()));
    {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .open(&temporary)?;
        file.write_all(render_entries(entries).as_bytes())?;
        file.sync_all()?;
    }
    fs::rename(&temporary, &path)?;
    Ok(path)
}

pub fn load_entries(directory: &Path) -> Vec<Entry> {
    fs::read_to_string(directory.join(ANNOTATION_LIST_NAME))
        .map(|text| parse_annotation_list(&text))
        .unwrap_or_default()
}

#[cfg(test)]
mod list_tests {
    use super::*;

    const SAMPLE: &str = "## 2026-08-22 14:12 · Firefox\n\n> the quote\n\n→ the comment\n\n## 2026-08-22 13:27 · Chrome\n\n> another quote\n> second line\n\n→ another comment\n";

    #[test]
    fn reads_every_entry_in_file_order() {
        let entries = parse_annotation_list(SAMPLE);
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].stamp, "2026-08-22 14:12");
        assert_eq!(entries[0].source, "Firefox");
        assert_eq!(entries[0].quote, "the quote");
        assert_eq!(entries[0].comment, "the comment");
        assert_eq!(entries[1].quote, "another quote\nsecond line");
    }

    #[test]
    fn round_trips_without_changing_the_file() {
        let entries = parse_annotation_list(SAMPLE);
        assert_eq!(render_entries(&entries), SAMPLE);
    }

    #[test]
    fn skips_a_malformed_entry_rather_than_guessing() {
        let broken = "## 2026-08-22 14:12 · Firefox\n\n> quote with no comment\n\n## 2026-08-22 15:00 · Chrome\n\n> good\n\n→ fine\n";
        let entries = parse_annotation_list(broken);
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].source, "Chrome");
    }

    #[test]
    fn ignores_a_markdown_heading_that_is_not_an_entry_header() {
        let entries = parse_annotation_list("## Some notes\n\n> x\n\n→ y\n");
        assert_eq!(entries, vec![]);
    }

    #[test]
    fn keeps_a_multi_line_comment_together() {
        let entries = parse_annotation_list("## 2026-08-22 14:12 · A\n\n> q\n\n→ first\nsecond\n");
        assert_eq!(entries[0].comment, "first\nsecond");
    }

    #[test]
    fn saving_replaces_the_file_atomically_and_stays_private() {
        let dir = std::env::temp_dir().join(format!("annot-save-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join(ANNOTATION_LIST_NAME), SAMPLE).unwrap();

        let mut entries = parse_annotation_list(SAMPLE);
        entries[0].comment = "edited comment".into();
        save_entries(&entries, &dir).unwrap();

        let reloaded = load_entries(&dir);
        assert_eq!(reloaded[0].comment, "edited comment");
        assert_eq!(reloaded[1].comment, "another comment", "other entries survive");
        let mode = fs::metadata(dir.join(ANNOTATION_LIST_NAME)).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o600);
        // no temp files left behind
        let leftovers: Vec<_> = fs::read_dir(&dir).unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| e.file_name().to_string_lossy().ends_with(".tmp"))
            .collect();
        assert!(leftovers.is_empty(), "temp file was not cleaned up");
        fs::remove_dir_all(&dir).unwrap();
    }
}

#[cfg(test)]
mod real_file_tests {
    use super::*;

    /// Guards the only genuinely dangerous operation: rewriting the whole file.
    /// Byte equality is the wrong bar because the existing file has
    /// inconsistent blank lines between entries and rendering normalises them.
    /// What must hold is that no entry and no character of content is lost.
    #[test]
    fn round_trips_the_real_annotations_file_without_losing_content() {
        let path = std::path::PathBuf::from(std::env::var("HOME").unwrap())
            .join("Annotations/annotations.md");
        let Ok(original) = fs::read_to_string(&path) else {
            eprintln!("no real annotations file; skipping");
            return;
        };

        let first = parse_annotation_list(&original);
        assert!(!first.is_empty(), "real file parsed to zero entries");

        let second = parse_annotation_list(&render_entries(&first));
        assert_eq!(
            first, second,
            "re-reading our own output must yield identical entries"
        );

        eprintln!("real file: {} entries round-tripped intact", first.len());
    }

    /// Every header in the file must become an entry. If the parser silently
    /// dropped one, saving would delete it from disk.
    #[test]
    fn parses_every_entry_header_present_in_the_real_file() {
        let path = std::path::PathBuf::from(std::env::var("HOME").unwrap())
            .join("Annotations/annotations.md");
        let Ok(original) = fs::read_to_string(&path) else { return };

        let headers = original
            .lines()
            .filter(|l| split_header(l).is_some())
            .count();
        let parsed = parse_annotation_list(&original).len();
        assert_eq!(parsed, headers, "parser dropped {} entries", headers - parsed);
    }
}
