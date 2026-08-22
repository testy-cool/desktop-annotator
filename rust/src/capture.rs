//! X11 capture, matching desktop_annotator/capture.py including the polling
//! deadline that replaced its fixed 180ms sleep.

use std::process::Command;
use std::time::{Duration, Instant};

pub const COPY_RESPONSE_TIMEOUT: Duration = Duration::from_millis(180);
pub const COPY_POLL_INTERVAL: Duration = Duration::from_millis(8);

pub struct Candidate {
    pub label: &'static str,
    pub text: String,
}

fn xclip_out(selection: &str) -> String {
    Command::new("xclip")
        .args(["-selection", selection, "-out"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
        .unwrap_or_default()
}

fn xclip_in(text: &str) -> bool {
    use std::io::Write;
    use std::process::Stdio;
    let Ok(mut child) = Command::new("xclip")
        .args(["-selection", "clipboard", "-in"])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    else {
        return false;
    };
    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(text.as_bytes());
    }
    true
}

pub fn primary() -> String {
    xclip_out("primary").trim().to_string()
}

pub fn clipboard() -> String {
    xclip_out("clipboard").trim().to_string()
}

/// Presses Ctrl+C in the focused window and waits only as long as that
/// application actually needs, giving up at COPY_RESPONSE_TIMEOUT. An empty
/// read counts as "not yet" because xclip also returns empty while clipboard
/// ownership is changing hands.
pub fn copy_focused_selection() -> String {
    let previous = clipboard();
    let sentinel = format!("desktop-annotator-{}", std::process::id());
    if !xclip_in(&sentinel) {
        return String::new();
    }
    std::thread::sleep(Duration::from_millis(20)); // let xclip take ownership

    let _ = Command::new("xdotool")
        .args(["key", "--clearmodifiers", "ctrl+c"])
        .output();

    let deadline = Instant::now() + COPY_RESPONSE_TIMEOUT;
    let mut copied = String::new();
    loop {
        let current = xclip_out("clipboard");
        if !current.is_empty() && current != sentinel {
            copied = current;
            break;
        }
        if Instant::now() >= deadline {
            break;
        }
        std::thread::sleep(COPY_POLL_INTERVAL);
    }

    xclip_in(&previous);
    copied.trim().to_string()
}

/// "Selected text" first, then the live clipboard when it differs — the same
/// two choices the GTK popup offers.
pub fn candidates() -> Vec<Candidate> {
    let clip = clipboard();
    let mut selection = primary();
    if selection.is_empty() {
        selection = copy_focused_selection();
    }

    let mut out = Vec::new();
    if !selection.is_empty() {
        out.push(Candidate { label: "Selected text", text: selection.clone() });
    }
    if !clip.is_empty() && clip != selection {
        out.push(Candidate { label: "Clipboard", text: clip });
    }
    out
}

pub fn active_window_title() -> String {
    Command::new("xdotool")
        .args(["getactivewindow", "getwindowname"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "Unknown window".into())
}

/// Matches workflow.annotation_source: a clipboard pick records both.
pub fn annotation_source(label: &str, window_title: &str) -> String {
    if label == "Clipboard" {
        format!("Clipboard · {window_title}")
    } else {
        window_title.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clipboard_pick_records_both_clipboard_and_window() {
        assert_eq!(
            annotation_source("Clipboard", "Firefox"),
            "Clipboard · Firefox"
        );
    }

    #[test]
    fn selection_pick_records_only_the_window() {
        assert_eq!(annotation_source("Selected text", "Firefox"), "Firefox");
    }
}
