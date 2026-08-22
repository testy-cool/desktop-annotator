//! Single-instance toggle, matching desktop_annotator/toggle.py: the second
//! launch signals the first to close instead of opening another window.

use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::unix::io::AsRawFd;
use std::path::PathBuf;

/// Holds the lock for the lifetime of this instance; dropping it releases the flock.
pub struct Instance {
    _lock: File,
}

pub fn lock_path() -> PathBuf {
    std::env::var("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/tmp"))
        .join("desktop-annotator.lock")
}

/// `Some` when this process should show a window. `None` when another instance
/// held the lock and has been told to close — this process must exit silently.
pub fn claim_or_toggle() -> std::io::Result<Option<Instance>> {
    let mut file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(lock_path())?;

    if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        let mut pid = String::new();
        file.read_to_string(&mut pid)?;
        if let Ok(pid) = pid.trim().parse::<i32>() {
            // ESRCH just means it exited between our failed lock and now.
            unsafe { libc::kill(pid, libc::SIGUSR1) };
        }
        return Ok(None);
    }

    file.set_len(0)?;
    file.seek(SeekFrom::Start(0))?;
    write!(file, "{}", std::process::id())?;
    file.flush()?;
    Ok(Some(Instance { _lock: file }))
}

/// SIGUSR1 means "another launch happened" -> quit. A signal handler cannot
/// safely touch the event loop, so a thread waits and posts the quit back.
pub fn quit_on_sigusr1() {
    std::thread::spawn(|| {
        let Ok(mut signals) =
            signal_hook::iterator::Signals::new([signal_hook::consts::SIGUSR1])
        else {
            eprintln!("cannot watch SIGUSR1; toggle will open a second window instead");
            return;
        };
        for _ in signals.forever() {
            let _ = slint::invoke_from_event_loop(|| {
                let _ = slint::quit_event_loop();
            });
        }
    });
}
