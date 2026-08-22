//! Ported from desktop_annotator/positioning.py, tests included.
//! Pure geometry: no windowing calls, so it stays testable off-screen.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MonitorRect {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

impl MonitorRect {
    fn center_x(&self) -> f64 {
        self.x as f64 + self.width as f64 / 2.0
    }

    fn center_y(&self) -> f64 {
        self.y as f64 + self.height as f64 / 2.0
    }

    /// Squared distance to a point, zero when the point is inside.
    fn distance_to(&self, x: i32, y: i32) -> i64 {
        let horizontal = (self.x - x).max(0).max(x - (self.x + self.width - 1)) as i64;
        let vertical = (self.y - y).max(0).max(y - (self.y + self.height - 1)) as i64;
        horizontal * horizontal + vertical * vertical
    }
}

pub fn monitor_for_pointer(monitors: &[MonitorRect], x: i32, y: i32) -> Option<MonitorRect> {
    monitors
        .iter()
        .min_by_key(|monitor| monitor.distance_to(x, y))
        .copied()
}

/// The nearest monitor whose centre is right of `current`, or `current` when it
/// is already the rightmost. Ties on horizontal distance break by vertical
/// closeness, so stacked side monitors pick the one level with you.
pub fn monitor_to_right(monitors: &[MonitorRect], current: MonitorRect) -> MonitorRect {
    monitors
        .iter()
        .filter(|monitor| monitor.center_x() > current.center_x())
        .min_by(|a, b| {
            let key = |m: &MonitorRect| {
                (
                    m.center_x() - current.center_x(),
                    (m.center_y() - current.center_y()).abs(),
                )
            };
            let (ax, ay) = key(a);
            let (bx, by) = key(b);
            ax.partial_cmp(&bx)
                .unwrap()
                .then(ay.partial_cmp(&by).unwrap())
        })
        .copied()
        .unwrap_or(current)
}

pub fn centered_window_position(monitor: MonitorRect, width: i32, height: i32) -> (i32, i32) {
    (
        monitor.x + ((monitor.width - width) / 2).max(0),
        monitor.y + ((monitor.height - height) / 2).max(0),
    )
}

pub fn popup_position(
    monitors: &[MonitorRect],
    pointer_x: i32,
    pointer_y: i32,
    width: i32,
    height: i32,
) -> Option<(i32, i32)> {
    let current = monitor_for_pointer(monitors, pointer_x, pointer_y)?;
    let target = monitor_to_right(monitors, current);
    Some(centered_window_position(target, width, height))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn three_monitors() -> Vec<MonitorRect> {
        vec![
            MonitorRect { x: 0, y: 0, width: 2560, height: 1440 },
            MonitorRect { x: 2560, y: 0, width: 1920, height: 1080 },
            MonitorRect { x: 4480, y: 0, width: 2560, height: 1440 },
        ]
    }

    #[test]
    fn finds_the_monitor_containing_the_pointer() {
        let monitors = three_monitors();
        assert_eq!(monitor_for_pointer(&monitors, 3000, 400), Some(monitors[1]));
    }

    #[test]
    fn chooses_the_nearest_monitor_to_the_right() {
        let monitors = three_monitors();
        assert_eq!(monitor_to_right(&monitors, monitors[0]), monitors[1]);
    }

    #[test]
    fn stays_on_the_current_monitor_when_none_is_to_its_right() {
        let monitors = three_monitors();
        assert_eq!(monitor_to_right(&monitors, monitors[2]), monitors[2]);
    }

    #[test]
    fn uses_nearest_vertical_neighbor_when_right_edges_are_equal() {
        let current = MonitorRect { x: 0, y: 1000, width: 1920, height: 1080 };
        let upper_right = MonitorRect { x: 1920, y: -200, width: 1920, height: 1080 };
        let lower_right = MonitorRect { x: 1920, y: 1000, width: 1920, height: 1080 };
        let monitors = vec![upper_right, current, lower_right];
        assert_eq!(monitor_to_right(&monitors, current), lower_right);
    }

    #[test]
    fn centers_the_window_on_the_target_monitor() {
        let monitor = MonitorRect { x: 2560, y: 0, width: 1920, height: 1080 };
        assert_eq!(centered_window_position(monitor, 720, 620), (3160, 230));
    }

    #[test]
    fn places_popup_on_monitor_to_the_right_of_the_pointer_monitor() {
        let monitors = vec![
            MonitorRect { x: 0, y: 0, width: 2560, height: 1440 },
            MonitorRect { x: 2560, y: 0, width: 1920, height: 1080 },
        ];
        assert_eq!(popup_position(&monitors, 1200, 700, 720, 620), Some((3160, 230)));
    }

    #[test]
    fn clamps_an_oversized_window_to_the_monitor_origin() {
        let monitor = MonitorRect { x: -1280, y: 0, width: 1280, height: 720 };
        assert_eq!(centered_window_position(monitor, 1600, 900), (-1280, 0));
    }
}
