"""The keyboard shortcuts, in one place. Templates mark the element a key acts on with
`data-shortcut`, taken from here; `static/frontdesk.js` does the rest. Browser keys such as
Ctrl+N, Ctrl+P and Ctrl+W are never used."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Shortcut:
    key: str
    label: str
    action: str
    where: str


SHORTCUTS: dict[str, Shortcut] = {
    s.key: s
    for s in (
        Shortcut("alt+n", "Alt+N", "Start a new visit", "Every screen"),
        Shortcut("alt+f", "Alt+F", "Find a patient", "Every screen"),
        Shortcut("alt+d", "Alt+D", "Open the dues list", "Every screen"),
        Shortcut("alt+s", "Alt+S", "Save", "Front-desk forms"),
        Shortcut("alt+r", "Alt+R", "Print the bill and receipt", "Visit summary"),
        Shortcut("f2", "F2", "Open the referrer list", "New visit"),
    )
}
