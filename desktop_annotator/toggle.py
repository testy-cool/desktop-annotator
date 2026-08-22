from __future__ import annotations

import fcntl
import os
import signal
from pathlib import Path
from types import FrameType
from typing import Callable


# SIGUSR1 looks like the obvious choice, but WebKit's JavaScript engine claims
# it for garbage collection and replaces any handler the process already had,
# which kills the window instead of toggling it.
TOGGLE_SIGNAL = signal.SIGUSR2

ToggleCallback = Callable[[], None]
SignalSender = Callable[[int, int], None]


def run_as_toggle_instance(instance, application: Callable[[ToggleInstance], int]) -> int:
    with instance:
        if not instance.claim_or_toggle():
            return 0
        return application(instance)


class ToggleInstance:
    def __init__(
        self, lock_path: Path, *, signal_sender: SignalSender = os.kill
    ) -> None:
        self.lock_path = lock_path
        self.signal_sender = signal_sender
        self._lock_file = None
        self._previous_signal_handler = None
        self._toggle_callback: ToggleCallback | None = None
        self._toggle_pending = False

    def claim_or_toggle(self) -> bool:
        self.lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_file = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.seek(0)
            existing_pid = lock_file.read().strip()
            lock_file.close()
            if existing_pid:
                self.signal_sender(int(existing_pid), TOGGLE_SIGNAL)
            return False

        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        os.fchmod(lock_file.fileno(), 0o600)
        self._lock_file = lock_file
        self._previous_signal_handler = signal.getsignal(TOGGLE_SIGNAL)
        signal.signal(TOGGLE_SIGNAL, self._receive_toggle)
        return True

    def set_toggle_callback(self, callback: ToggleCallback) -> None:
        self._toggle_callback = callback
        if self._toggle_pending:
            self._toggle_pending = False
            callback()

    def _receive_toggle(
        self, _signum: int, _frame: FrameType | None
    ) -> None:
        if self._toggle_callback is None:
            self._toggle_pending = not self._toggle_pending
            return
        self._toggle_callback()

    def close(self) -> None:
        if self._lock_file is None:
            return
        if self._previous_signal_handler is not None:
            signal.signal(TOGGLE_SIGNAL, self._previous_signal_handler)
        fcntl.flock(self._lock_file, fcntl.LOCK_UN)
        self._lock_file.close()
        self._lock_file = None

    def __enter__(self) -> ToggleInstance:
        return self

    def __exit__(self, *_args) -> None:
        self.close()
