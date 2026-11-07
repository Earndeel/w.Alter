---
name: hermes-config-extra-pitfall
description: "Platform config keys that must live under extra — port and host pitfall for gateway adapters."
category: devops
tags: [hermes, config, gateway, pitfall]
---

# Platform Config — The `extra` Pitfall

## Problem

Some gateway platform adapters read configuration from `config.extra`, not
from top-level keys in the platform block. When `host` and `port` are set
outside `extra`, the adapter silently ignores them and falls back to defaults.

## Affected adapters

- `api_server` — reads `host`, `port`, `key`, `cors_origins` from `extra`
- Plugin adapters may have the same contract

## Why

The shared-key bridging loop in `gateway/config.py::load_gateway_config`
only forwards specific known keys (`allow_from`, `require_mention`, etc.)
into `extra`. `host` and `port` are not in that list.

## Correct format

```yaml
gateway:
  platforms:
    api_server:
      enabled: true
      extra:
        host: "0.0.0.0"
        port: 9120
```

## Incorrect (silently ignored)

```yaml
gateway:
  platforms:
    api_server:
      enabled: true
      host: "0.0.0.0"
      port: 9120
```

The adapter uses `DEFAULT_PORT` (8642) and `DEFAULT_HOST` instead.

## Detection

When the dashboard status endpoint reports a different port than the
gateway actual listening port, check whether `host` and `port` are under
`extra` in `config.yaml`.
