# Device Context

Stable facts live in Operator configuration/runtime, not conversation memory or task state. Request `computer_use(action="device_context")` only when device capabilities matter; atomic Operator actions already return its compact summary.

Expected compact fields: device identity, platform, transport, AX/pixels/background-input availability, and current presence signal. Never store the current goal, semantic progress, prior reasoning, or workflow routes here.
