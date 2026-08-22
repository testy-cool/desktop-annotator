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
