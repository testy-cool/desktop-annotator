import unittest

from desktop_annotator.positioning import (
    MonitorRect,
    centered_window_position,
    monitor_for_pointer,
    monitor_to_right,
    popup_position,
)


class MonitorSelectionTests(unittest.TestCase):
    def setUp(self):
        self.monitors = [
            MonitorRect(x=0, y=0, width=2560, height=1440),
            MonitorRect(x=2560, y=0, width=1920, height=1080),
            MonitorRect(x=4480, y=0, width=2560, height=1440),
        ]

    def test_finds_the_monitor_containing_the_pointer(self):
        monitor = monitor_for_pointer(self.monitors, x=3000, y=400)

        self.assertEqual(monitor, self.monitors[1])

    def test_chooses_the_nearest_monitor_to_the_right(self):
        monitor = monitor_to_right(self.monitors, self.monitors[0])

        self.assertEqual(monitor, self.monitors[1])

    def test_stays_on_the_current_monitor_when_none_is_to_its_right(self):
        monitor = monitor_to_right(self.monitors, self.monitors[2])

        self.assertEqual(monitor, self.monitors[2])

    def test_uses_nearest_vertical_neighbor_when_right_edges_are_equal(self):
        current = MonitorRect(x=0, y=1000, width=1920, height=1080)
        upper_right = MonitorRect(x=1920, y=-200, width=1920, height=1080)
        lower_right = MonitorRect(x=1920, y=1000, width=1920, height=1080)

        monitor = monitor_to_right([upper_right, current, lower_right], current)

        self.assertEqual(monitor, lower_right)


class PopupPositionTests(unittest.TestCase):
    def test_centers_the_window_on_the_target_monitor(self):
        monitor = MonitorRect(x=2560, y=0, width=1920, height=1080)

        position = centered_window_position(monitor, width=720, height=620)

        self.assertEqual(position, (3160, 230))

    def test_places_popup_on_monitor_to_the_right_of_the_pointer_monitor(self):
        monitors = [
            MonitorRect(x=0, y=0, width=2560, height=1440),
            MonitorRect(x=2560, y=0, width=1920, height=1080),
        ]

        position = popup_position(monitors, pointer_x=1200, pointer_y=700, width=720, height=620)

        self.assertEqual(position, (3160, 230))

    def test_clamps_an_oversized_window_to_the_monitor_origin(self):
        monitor = MonitorRect(x=-1280, y=0, width=1280, height=720)

        position = centered_window_position(monitor, width=1600, height=900)

        self.assertEqual(position, (-1280, 0))


if __name__ == "__main__":
    unittest.main()
