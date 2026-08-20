import os
import signal
import tempfile
import unittest
from pathlib import Path

from desktop_annotator.toggle import ToggleInstance, run_as_toggle_instance


class ToggleInstanceTests(unittest.TestCase):
    def test_second_instance_signals_the_existing_instance_instead_of_claiming(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            lock_path = Path(temporary_directory) / "annotator.lock"
            sent_signals = []
            first = ToggleInstance(lock_path)
            second = ToggleInstance(
                lock_path,
                signal_sender=lambda pid, signum: sent_signals.append((pid, signum)),
            )
            self.addCleanup(first.close)
            self.addCleanup(second.close)

            self.assertTrue(first.claim_or_toggle())
            self.assertFalse(second.claim_or_toggle())

            self.assertEqual(sent_signals, [(os.getpid(), signal.SIGUSR1)])

    def test_toggle_signal_runs_the_registered_callback(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            instance = ToggleInstance(Path(temporary_directory) / "annotator.lock")
            self.addCleanup(instance.close)
            toggled = []

            self.assertTrue(instance.claim_or_toggle())
            instance.set_toggle_callback(lambda: toggled.append(True))
            signal.raise_signal(signal.SIGUSR1)

            self.assertEqual(toggled, [True])

    def test_second_invocation_exits_without_running_the_application(self):
        class ExistingInstance:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def claim_or_toggle(self):
                return False

        application_runs = []

        exit_code = run_as_toggle_instance(
            ExistingInstance(), lambda _instance: application_runs.append(True) or 1
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(application_runs, [])

    def test_toggle_received_before_callback_registration_is_not_lost(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            instance = ToggleInstance(Path(temporary_directory) / "annotator.lock")
            self.addCleanup(instance.close)
            toggled = []

            self.assertTrue(instance.claim_or_toggle())
            signal.raise_signal(signal.SIGUSR1)
            instance.set_toggle_callback(lambda: toggled.append(True))

            self.assertEqual(toggled, [True])


if __name__ == "__main__":
    unittest.main()
