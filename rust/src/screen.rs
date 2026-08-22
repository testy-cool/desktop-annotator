//! Monitor geometry and pointer location.
//!
//! Slint exposes set_position but no monitor enumeration, so the layout comes
//! from xrandr and the pointer from xdotool — the same two X11 tools the Python
//! app already depends on. Parsing is split from the subprocess calls so the
//! formats can be tested against real captured output.

use crate::positioning::MonitorRect;
use std::process::Command;

/// Parses `xrandr --listmonitors`, whose geometry field looks like
/// `2560/597x1440/336+0+0` — pixels/millimetres for each axis, then the offset.
pub fn parse_listmonitors(output: &str) -> Vec<MonitorRect> {
    output
        .lines()
        .skip(1) // "Monitors: N"
        .filter_map(|line| {
            let geometry = line.split_whitespace().nth(2)?;
            let mut parts = geometry.split('+');
            let size = parts.next()?;
            let x = parts.next()?.parse().ok()?;
            let y = parts.next()?.parse().ok()?;
            let (w, h) = size.split_once('x')?;
            Some(MonitorRect {
                x,
                y,
                width: w.split('/').next()?.parse().ok()?,
                height: h.split('/').next()?.parse().ok()?,
            })
        })
        .collect()
}

/// Parses `xdotool getmouselocation`, e.g. `x:825 y:851 screen:0 window:1234`.
pub fn parse_mouse_location(output: &str) -> Option<(i32, i32)> {
    let mut x = None;
    let mut y = None;
    for field in output.split_whitespace() {
        match field.split_once(':') {
            Some(("x", value)) => x = value.parse().ok(),
            Some(("y", value)) => y = value.parse().ok(),
            _ => {}
        }
    }
    Some((x?, y?))
}

fn run(program: &str, args: &[&str]) -> Option<String> {
    let output = Command::new(program).args(args).output().ok()?;
    output
        .status
        .success()
        .then(|| String::from_utf8_lossy(&output.stdout).into_owned())
}

pub fn monitors() -> Vec<MonitorRect> {
    run("xrandr", &["--listmonitors"])
        .map(|out| parse_listmonitors(&out))
        .unwrap_or_default()
}

pub fn pointer() -> Option<(i32, i32)> {
    parse_mouse_location(&run("xdotool", &["getmouselocation"])?)
}

#[cfg(test)]
mod tests {
    use super::*;

    // Captured verbatim from the development machine, three monitors.
    const LISTMONITORS: &str = "Monitors: 3
 0: +*DP-2 2560/597x1440/336+0+0  DP-2
 1: +HDMI-0 1920/521x1080/293+2560+0  HDMI-0
 2: +DP-0 2560/600x1440/340+4480+0  DP-0";

    #[test]
    fn reads_every_monitor_with_its_offset() {
        let monitors = parse_listmonitors(LISTMONITORS);
        assert_eq!(
            monitors,
            vec![
                MonitorRect { x: 0, y: 0, width: 2560, height: 1440 },
                MonitorRect { x: 2560, y: 0, width: 1920, height: 1080 },
                MonitorRect { x: 4480, y: 0, width: 2560, height: 1440 },
            ]
        );
    }

    #[test]
    fn ignores_the_millimetre_figures_in_the_geometry_field() {
        // 597 and 336 are physical millimetres, not pixels.
        let monitors = parse_listmonitors(LISTMONITORS);
        assert_eq!(monitors[0].width, 2560);
        assert_eq!(monitors[0].height, 1440);
    }

    #[test]
    fn handles_a_negative_offset_from_a_monitor_placed_left() {
        // xrandr writes a left-of-origin monitor as "+-1280+0".
        let monitors = parse_listmonitors("Monitors: 1\n 0: +DP-1 1280/300x720/200+-1280+0  DP-1");
        assert_eq!(
            monitors,
            vec![MonitorRect { x: -1280, y: 0, width: 1280, height: 720 }]
        );
    }

    #[test]
    fn returns_nothing_when_xrandr_is_unavailable() {
        assert_eq!(parse_listmonitors(""), vec![]);
    }

    #[test]
    fn reads_the_pointer_position() {
        assert_eq!(
            parse_mouse_location("x:825 y:851 screen:0 window:125829124"),
            Some((825, 851))
        );
    }

    #[test]
    fn rejects_pointer_output_missing_a_coordinate() {
        assert_eq!(parse_mouse_location("screen:0 window:1"), None);
    }
}
