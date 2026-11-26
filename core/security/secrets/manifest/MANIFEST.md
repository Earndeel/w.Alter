# Walter Secrets

**Role.** Use of {{owner.address}}'s whole Bitwarden vault — logins, API keys, cards, codes received by e-mail or
Beeper — while no secret value enters a model, a journal, a prompt or a URL.

**Organisation.** Bitwarden access with a shared session (`walter-secrets-sync`), a model-safe API (metadata,
references), local execution, received codes, and W.Alter's grants per account (`walter-secret grants`: which
component may read which key).

**Use**
1. `secret_search(query, kind)`: find the entry (metadata only).
2. `secret_reference(item, field)`: a reference, without the value.
3. Locally: `walter-secret exec --bind VAR=<reference> -- <command>`; the value exists only inside the launched
   process. Received code: `walter-secret otp <site>`.

**Rules**: never run `bw unlock` directly; never put a secret in a prompt, an answer, a URL, a command argument or a
systemd unit; API keys are read through grants, never written to a file.
