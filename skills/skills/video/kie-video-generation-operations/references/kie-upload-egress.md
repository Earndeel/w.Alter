# Kie upload egress: Oracle agent via authorized Mac

## Trigger

Use this path when a Kie credential probe succeeds but the binary upload endpoint returns an edge-level `HTTP 403` (observed `error code: 1010`) from an Oracle-hosted agent.

## Root-cause check

1. Read `KIE_API_KEY` from the vault in memory; never print it or put it in a command argument.
2. Probe the authenticated main API with a harmless invalid record ID:
   `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=auth-probe-invalid`
3. Interpret `HTTP 200` with an API-level invalid-record response (for example `code=422`, `recordInfo is null`) as evidence that the credential is accepted. Do not rotate a valid key merely because upload fails.
4. Confirm the official upload contract remains:
   `POST https://kieai.redpandaai.co/api/file-stream-upload`
   with `Authorization: Bearer ...` and multipart fields `file`, `uploadPath`, `fileName`.

## Working transport

Use a temporary SSH SOCKS5 tunnel through an authorized Mac; the key stays on the Linux agent:

```bash
ssh -N -o ExitOnForwardFailure=yes -D 18080 \
  -i /root/.ssh/id_ed25519 \
  lucasjouvencon@100.127.150.1 &
export KIE_SOCKS_PROXY='socks5h://127.0.0.1:18080'
```

The provider upload adapter should pass `KIE_SOCKS_PROXY` (or `KIE_HTTP_PROXY`) to a multipart HTTP client with SOCKS support, such as `requests[socks]`. Keep the tunnel lifecycle in a wrapper: wait for the local port, run the provider command, then terminate the SSH process in an `EXIT` trap. Do not use `exec` for the child command when the parent shell owns cleanup.

The Creative Factory wrapper is:
`/root/.hermes/profiles/creative-factory/scripts/kie_via_mac.sh`

## Verification boundary

A valid fix produces:

- upload `HTTP 200` and provider `code=200`;
- a temporary `downloadUrl` recorded in an upload receipt;
- no API key in output or artifacts;
- `task_submitted=false` until the approved generation gate explicitly authorizes `createTask`.

Kie upload URLs are temporary. Re-upload the asset immediately before paid task submission if the receipt may have expired. An upload success is not a generated video and must not be reported as one.
