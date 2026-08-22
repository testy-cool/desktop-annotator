mod annotation;
mod capture;
mod instance;
mod positioning;
mod screen;

use annotation::Annotation;
use std::process::Command;

slint::include_modules!();

const WIDTH: i32 = 720;
const HEIGHT: i32 = 440;

/// Formatted via `date` so the crate stays dependency-free on time handling;
/// annotation::render_annotation takes the finished string.
fn timestamp() -> String {
    Command::new("date")
        .arg("+%Y-%m-%d %H:%M")
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_default()
}

fn notify(body: &str) {
    let _ = Command::new("notify-send")
        .args(["-a", "Desktop Annotator", "Desktop Annotator", body])
        .status();
}

/// $VISUAL, then $EDITOR, then subl, then xdg-open.
fn open_in_editor(path: &std::path::Path) {
    let explicit = std::env::var("VISUAL").or_else(|_| std::env::var("EDITOR")).ok();
    let candidates: Vec<String> = explicit
        .into_iter()
        .chain(["subl".to_string(), "xdg-open".to_string()])
        .collect();
    for program in candidates {
        if Command::new(&program).arg(path).spawn().is_ok() {
            return;
        }
    }
    notify("Could not find an editor to open annotations.md");
}

fn place_on_monitor_to_the_right(window: &slint::Window) {
    let monitors = screen::monitors();
    let Some((px, py)) = screen::pointer() else { return };
    let Some((x, y)) = positioning::popup_position(&monitors, px, py, WIDTH, HEIGHT) else {
        return;
    };
    window.set_position(slint::PhysicalPosition::new(x, y));
}

fn main() -> Result<(), slint::PlatformError> {
    let _instance = match instance::claim_or_toggle() {
        Ok(Some(instance)) => Some(instance),
        Ok(None) => return Ok(()), // told the running popup to close
        Err(e) => {
            eprintln!("single-instance lock unavailable ({e}); opening anyway");
            None
        }
    };
    instance::quit_on_sigusr1();

    let window_title = capture::active_window_title();
    let candidates = capture::candidates();
    if candidates.is_empty() {
        notify("Nothing to annotate. Select or copy some text first.");
        return Ok(());
    }

    let stamp = timestamp();
    let directory = annotation::annotations_dir();

    let ui = Popup::new()?;
    ui.set_stamp(stamp.clone().into());
    ui.set_quote(candidates[0].text.clone().into());
    ui.set_source(capture::annotation_source(candidates[0].label, &window_title).into());
    ui.set_candidate_labels(slint::ModelRc::new(slint::VecModel::from(
        candidates
            .iter()
            .map(|c| slint::SharedString::from(c.label))
            .collect::<Vec<_>>(),
    )));

    ui.window().set_position(slint::PhysicalPosition::new(0, 0));
    place_on_monitor_to_the_right(ui.window());

    // switching capture source
    {
        let weak = ui.as_weak();
        let texts: Vec<(String, String)> = candidates
            .iter()
            .map(|c| (c.text.clone(), capture::annotation_source(c.label, &window_title)))
            .collect();
        ui.on_pick(move |index| {
            let Some(ui) = weak.upgrade() else { return };
            let Some((text, source)) = texts.get(index as usize) else { return };
            ui.set_candidate(index);
            ui.set_quote(text.clone().into());
            ui.set_source(source.clone().into());
        });
    }

    // saving
    {
        let weak = ui.as_weak();
        let directory = directory.clone();
        let stamp = stamp.clone();
        ui.on_save(move || {
            let Some(ui) = weak.upgrade() else { return };
            let comment = ui.get_comment().to_string();
            if comment.trim().is_empty() {
                ui.set_status("Write a comment before adding this entry.".into());
                return;
            }
            let entry = Annotation {
                quote: ui.get_quote().to_string(),
                comment: comment.trim().to_string(),
                source: ui.get_source().to_string(),
                captured_at: stamp.clone(),
            };
            match annotation::append_annotation(&entry, &directory) {
                Ok(_) => {
                    let _ = slint::quit_event_loop();
                }
                Err(e) => ui.set_status(format!("Could not save: {e}").into()),
            }
        });
    }

    // open the file in an editor, replacing the old List tab
    {
        let weak = ui.as_weak();
        let directory = directory.clone();
        ui.on_open_file(move || {
            let _ = weak.upgrade();
            open_in_editor(&directory.join(annotation::ANNOTATION_LIST_NAME));
            let _ = slint::quit_event_loop();
        });
    }

    {
        let weak = ui.as_weak();
        ui.on_drag_by(move |dx, dy| {
            let Some(ui) = weak.upgrade() else { return };
            let win = ui.window();
            let scale = win.scale_factor();
            let pos = win.position();
            win.set_position(slint::PhysicalPosition::new(
                pos.x + (dx * scale).round() as i32,
                pos.y + (dy * scale).round() as i32,
            ));
        });
    }

    ui.on_dismiss(|| {
        let _ = slint::quit_event_loop();
    });

    ui.show()?;
    slint::run_event_loop()?;
    Ok(())
}
