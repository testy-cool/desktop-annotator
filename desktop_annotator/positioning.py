from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class MonitorRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height

    def distance_to(self, x: int, y: int) -> int:
        horizontal = max(self.x - x, 0, x - (self.x + self.width - 1))
        vertical = max(self.y - y, 0, y - (self.y + self.height - 1))
        return horizontal * horizontal + vertical * vertical


def monitor_for_pointer(monitors: Sequence[MonitorRect], x: int, y: int) -> MonitorRect:
    if not monitors:
        raise ValueError("At least one monitor is required")
    return min(monitors, key=lambda monitor: monitor.distance_to(x, y))


def monitor_to_right(
    monitors: Sequence[MonitorRect], current: MonitorRect
) -> MonitorRect:
    candidates = [monitor for monitor in monitors if monitor.center_x > current.center_x]
    if not candidates:
        return current
    return min(
        candidates,
        key=lambda monitor: (
            monitor.center_x - current.center_x,
            abs(monitor.center_y - current.center_y),
        ),
    )


def centered_window_position(
    monitor: MonitorRect, *, width: int, height: int
) -> tuple[int, int]:
    x = monitor.x + max(0, (monitor.width - width) // 2)
    y = monitor.y + max(0, (monitor.height - height) // 2)
    return x, y


def popup_position(
    monitors: Sequence[MonitorRect],
    *,
    pointer_x: int,
    pointer_y: int,
    width: int,
    height: int,
) -> tuple[int, int]:
    current = monitor_for_pointer(monitors, pointer_x, pointer_y)
    target = monitor_to_right(monitors, current)
    return centered_window_position(target, width=width, height=height)
