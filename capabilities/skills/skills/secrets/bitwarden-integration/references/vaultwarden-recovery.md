# Vaultwarden self-hosted recovery

Use this reference when a self-hosted Vaultwarden instance is healthy over HTTPS but clients fail because the server/web-vault is too old or the host's SSH access is unavailable.

## Guardrails

- Establish server truth first: run `bw-unlock --sync`, make an encrypted export, and query `/api/config`; never delete client data or reinstall before proving the server state.
- Prefer CLI/API over GUI automation. If screen capture is black or macOS TCC/Accessibility rejects keystrokes, stop blind typing and give the user one short, copy-only command at a time.
- Do **not** put `set -e` in an interactive Cloud Shell block. A validation error (for example, a GCP resource-name error) can exit the user's shell. Use one side effect per block and inspect its output before continuing.
- Never paste browser metadata such as `@url:...` into a shell. Tell the user to copy only the code block.
- Do not claim access because GCP printed `Updated`; verify with a real SSH login from the controller host.

## GCP recovery sequence

Use placeholders for the project, instance, zone, public IP, and a newly generated temporary Ed25519 key. Never reuse a permanent key when a temporary recovery key is sufficient.

1. Identify the exact instance and zone:

   ```bash
   gcloud compute instances list --project="$PROJECT" \
     --format='table(name,zone,status,networkInterfaces[0].accessConfigs[0].natIP)'
   ```

2. Snapshot the boot disk before changing metadata. GCE snapshot names are lowercase letters, digits, and hyphens only; uppercase `T`/`Z` is rejected. Use uppercase `%S` for seconds and lowercase literal separators:

   ```bash
   DISK_URL=$(gcloud compute instances describe "$INSTANCE" \
     --project="$PROJECT" --zone="$ZONE" \
     --format='value(disks[0].source)')
   DISK=${DISK_URL##*/}
   SNAPSHOT="${INSTANCE}-pre-recovery-$(date -u +%Y%m%dt%H%M%Sz)"
   gcloud compute disks snapshot "$DISK" \
     --project="$PROJECT" --zone="$ZONE" \
     --snapshot-names="$SNAPSHOT" --quiet
   ```

3. Try metadata SSH without destroying existing keys. Read the current `ssh-keys` value, append a line for a temporary user, and set instance-level `enable-oslogin=FALSE` and `block-project-ssh=FALSE` only for recovery. Save the original startup script before replacing it.

4. Test the new key directly from the controller:

   ```bash
   ssh -i "$RECOVERY_KEY" -o IdentitiesOnly=yes \
     -o StrictHostKeyChecking=no "$RECOVERY_USER@$PUBLIC_IP" 'id -u; id -nG'
   ```

   A real login is the acceptance test. Retry for a short, bounded interval to allow the guest agent to poll metadata.

5. If the key is still rejected, metadata SSH is being ignored (commonly OS Login, project SSH blocking, or a guest-agent/user-creation issue). Install a temporary startup script that creates the recovery user, installs only the temporary public key, grants temporary sudo, and writes a marker; then perform a controlled reset:

   ```bash
   gcloud compute instances add-metadata "$INSTANCE" \
     --project="$PROJECT" --zone="$ZONE" \
     --metadata-from-file=startup-script=/tmp/recovery-startup.sh \
     --metadata='enable-oslogin=FALSE,block-project-ssh=FALSE' --quiet
   gcloud compute instances reset "$INSTANCE" \
     --project="$PROJECT" --zone="$ZONE" --quiet
   ```

   Ensure `--zone="$ZONE"` is a separate argument; a concatenated value such as `--quiet$ZONE` is invalid. Wait for the VM to return and repeat the direct SSH test.

## Safe Vaultwarden update

After SSH is verified:

1. Inspect only non-secret state: container names/images/status, Compose working directory, persistent mount sources/destinations, and disk free space. Do not print container environment variables or the data directory.
2. Confirm the persistent Vaultwarden data mount and create a snapshot before modifying the service.
3. Detect the available Compose CLI. Use `docker compose` if the v2 plugin exists; otherwise use the installed `docker-compose` binary. Do not assume the plugin is present and do not update unrelated services.
4. From the Compose working directory, update only Vaultwarden:

   ```bash
   sudo <compose> pull vaultwarden
   sudo <compose> up -d vaultwarden
   ```

   Preserve the existing data mount. Do not run `down`, prune images, or recreate Caddy unless the service requires it.
5. Verify the real path, not just the pull output:

   ```bash
   curl -fsSL https://<server>/api/config
   curl -fsS -o /dev/null -w 'alive_http=%{http_code}\n' https://<server>/alive
   sudo docker inspect vaultwarden --format='status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}'
   sudo docker image inspect vaultwarden/server:latest \
     --format='oci_version={{index .Config.Labels "org.opencontainers.image.version"}}'
   ```

   Require the expected compatibility floor (Vaultwarden 1.37.0+ for the Bitwarden 2026.7.x client), `/alive` HTTP 200, and Docker health `healthy` before reporting success.

## Cleanup and acceptance

- Remove the temporary user, its sudoers file, marker, and local temporary private key after verification.
- Restore the original `startup-script` from the saved file; remove the metadata key if it was originally absent.
- Remove only the recovery line from `ssh-keys`, preserving all original lines. Remove instance-level `enable-oslogin` and `block-project-ssh` overrides so project defaults apply again.
- Re-test `/alive`, `/api/config`, and Docker health after cleanup. Keep the pre-recovery snapshot and encrypted vault export until the client has synced and the item count is confirmed.
- For a client-side workaround while the server is being repaired, use a client version known to work with the old server (for this incident, Bitwarden 2026.6.1); prefer the server update as the permanent fix.
