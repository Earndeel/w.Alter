---
name: apple-automation-suite
description: "Unified suite for automating macOS native services: Apple Notes, Apple Reminders, FindMy, iMessage, and desktop computer-use tools via AppleScript and CLI."
version: 1.0.0
author: Orchestra Research
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [macOS, Apple, AppleScript, Reminders, Notes, iMessage, FindMy, Computer Use, Automation]
---

# macOS Native Automation & Integration

A consolidated, class-level suite containing AppleScript snippets, terminal command lines, and automation blueprints for native macOS system services.

*Note: This skill suite requires macOS host environment and will fail on Linux/Windows backends.*

---

## 1. AppleScript Execution Patterns

All macOS native application automations route through the Open Scripting Architecture (OSA) via terminal command `osascript`.

```bash
# Execute simple AppleScript from bash
osascript -e 'display dialog "Hello from Hermes Agent!"'
```

---

## 2. Integrated Services Blueprints

### A. Apple Notes & Reminders
Interact with calendars, lists, and pages via system events or database queries:
```bash
# Add a reminder to Default list
osascript -e 'tell application "Reminders" to make new reminder with properties {name:"Review code PR", due date:current date + (1 * hours)}'
```

### B. iMessage CLI Dispatcher
Send automated text messages through Messages app:
```bash
# Dispatch text message to active thread
osascript -e 'tell application "Messages" to send "Build succeeded!" to buddy "+15551234567"'
```

### C. FindMy Location Tracking
Extract cached geolocations via local terminal logs or Apple geocoder services.

---

## 3. macOS Computer Use & Screen Control

When using desktop automation, leverage remote CLI control or low-level keyboard/mouse tools:
- **screencapture:** Native utility for screenshots.
- **cliclick:** Recommended CLI mouse simulator for programmatic clicking.

```bash
# Capture full screen safely
screencapture -x /tmp/screen.png
```

---

## Support Directory Map
- `references/notes.md`: Detailed AppleScript syntax for creating, formatting, and reading Apple Notes documents.
- `references/reminders.md`: Automation snippets for scheduling, editing, and listing task notifications.
- `references/findmy.md`: Scripts and patterns for tracking device geolocations locally.
- `references/imessage.md`: Sending and reading text messages programmatically via native sqlite databases.
- `references/macos-computer-use.md`: Complete screencapture, cliclick, and GUI scripting blueprints.
