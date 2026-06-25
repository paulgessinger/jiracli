"""Desktop notifications via the OSC 9 terminal escape sequence.

``ESC ] 9 ; <text> BEL`` is the desktop-notification sequence understood by
Ghostty, kitty, WezTerm and iTerm2. It needs no subprocess and works over SSH
(the notification appears on the machine running the terminal emulator).
Terminals without support simply ignore it. Any failure is swallowed so
notifications never disrupt the TUI.
"""

from __future__ import annotations

import os
import sys

APP_TITLE = "jiracli"


def osc_supported() -> bool:
    """Heuristically detect terminals known to honour OSC 9 notifications."""
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    term = os.environ.get("TERM", "").lower()
    if term_program in {"ghostty", "wezterm", "iterm.app"}:
        return True
    if "kitty" in term or "ghostty" in term:
        return True
    if os.environ.get("KITTY_WINDOW_ID"):
        return True
    if os.environ.get("WEZTERM_PANE") or os.environ.get("WEZTERM_EXECUTABLE"):
        return True
    if os.environ.get("GHOSTTY_RESOURCES_DIR") or os.environ.get("GHOSTTY_BIN_DIR"):
        return True
    return False


def osc9_sequence(message: str, title: str = APP_TITLE) -> str:
    """Build the OSC 9 notification escape sequence for the given text."""
    text = f"{title}: {message}" if title else message
    # Strip controls that would terminate or corrupt the escape sequence.
    clean = text.replace("\x1b", " ").replace("\x07", " ").replace("\n", " ").strip()
    return f"\x1b]9;{clean}\x07"


def emit_to_tty(seq: str) -> bool:
    """Write an escape sequence straight to the controlling terminal.

    Used outside of a running Textual app; inside the app the sequence must be
    written through the Textual driver instead so it is correctly interleaved
    with the rendered frames (see ``JiraTUI._emit_notification``).
    """
    try:
        with open("/dev/tty", "wb", buffering=0) as tty:
            tty.write(seq.encode())
        return True
    except OSError:
        try:
            sys.stdout.buffer.write(seq.encode())
            sys.stdout.buffer.flush()
            return True
        except Exception:
            return False
