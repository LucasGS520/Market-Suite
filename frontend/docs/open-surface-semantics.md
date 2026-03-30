# Open Surface Semantics

This document defines the default semantic rule for open surfaces in the frontend.

## Categories

| Component | Category | Uses backdrop | Uses global blur | Intent |
| --- | --- | --- | --- | --- |
| `Dialog`, confirmation flows, lock screens | Blocking overlay | Yes | Yes | Isolate a critical decision or task |
| Priority `Drawer` | Blocking overlay | Yes | Yes | Redirect focus to a higher-priority flow |
| `Select`, `Menu`, `Popover`, contextual dropdowns | Contextual surface | No | No | Show local options without breaking page context |
| Small interactive section blocks | Contextual surface | No | No | Keep interactions light, local, and direct |

## System Rules

- A component that does not block a task or require a critical decision must not look like a modal.
- Modal tokens and modal surface styles must not be reused by `Select`, `Menu`, `Popover`, or contextual dropdowns.
- Contextual surfaces must keep the surrounding UI visible and readable.
- Local overrides are allowed for density, width, and alignment only. They must not change a contextual component into a blocking overlay.

## Review Checklist

- Does this component interrupt the user flow? If not, it must remain contextual.
- Does it darken or blur the full page? If yes, it is behaving like a blocking overlay.
- Can the user still understand the surrounding section while it is open? This must remain true for contextual surfaces.
