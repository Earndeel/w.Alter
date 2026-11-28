# Safari

Safari is a native device surface when interacting with the user's browser session. Native `open_url` can request navigation and return process/window/AX facts; it does not prove page content or user-task completion.

Prefer AX for toolbar, address field, tabs, and ordinary page controls when exposed. Use targeted pixels only when AX evidence is insufficient. Treat sheets, privacy prompts, restored-session dialogs, and missing windows as live observations for Hermes to interpret.
