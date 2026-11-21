# Profile isolation and effective-tool verification

## Tested pattern

Create the worker without bundled skills, then write a profile-local configuration instead of cloning the default profile:

```bash
hermes profile create video-factory --no-skills \
  --description "Autonomous branded-video production worker."
```

Create only the production directories, set `memory_enabled: false` unless production memory is explicitly designed, and keep `.env` and `auth.json` mode `0600`.

A minimal CLI tool allowlist is:

```yaml
platform_toolsets:
  cli:
    - file
    - terminal
    - code_execution
    - vision
    - image_gen
    - skills
```

Also disable inherited `bfl`, `web`, `browser`, `video_gen`, `x_search`, `tts`, `delegation`, `cronjob`, `memory`, and messaging integrations when they are not part of the worker contract. Verify with the profile wrapper:

```bash
video-factory profile show video-factory
video-factory tools list
video-factory config check
```

## Credential rule

A newly created profile may have no usable provider credential state. Copy only the required credential pool entries or run the profile-specific auth flow. Do not copy the entire default profile state, personal memory, session history, or messaging tokens.

For Google, a profile-local `google_token.json` and `google_client_secret.json` let standalone skill scripts follow `HERMES_HOME` without relying on the default profile. Never print their contents.

## Verification

Confirm:

- `hermes profile list` still shows all pre-existing profiles unchanged;
- the worker's `hermes profile show` reports the intended model and isolated path;
- the effective tool list contains only the allowlist plus Hermes-required core plumbing;
- `config check` passes;
- no provider secret appears in a status summary or log.
