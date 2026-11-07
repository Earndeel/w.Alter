# Host storage inventory and cleanup candidates

## 1. Establish the scope without changing state

Resolve the actual host, active Hermes home, checkout and service owner. Keep an explanation request read-only; do not update software, restart services, prune Docker or delete data. Load the Docker skill when container detail is needed.

Record `df -B1 /` and, on GNU/Linux, `du -x -B1 --max-depth=1 /` to compare filesystem allocation with directory usage. Use `-x` to avoid descending into other filesystems and Docker overlay mounts. Report inaccessible paths and scan errors rather than treating missing results as zero.

## 2. Descend into the largest consumers

Run a separate `du -x -B1 --max-depth=1 <directory>` invocation for each selected directory, sorting numerically. For example:

```sh
for p in /root /var /root/.cache; do
    du -x -B1 --max-depth=1 "$p" | sort -nr
done
```

Substitute the observed home instead of assuming `/root`. Do not pass overlapping ancestors and descendants to one `du` invocation: its inode deduplication can suppress later results. Include hidden directories; a shell `*` inventory misses major cache and environment consumers. Inspect large direct files separately with filesystem metadata because depth-one directory listings do not itemize them.

Drill into the active Hermes home, cache directories, package-manager stores, Docker root, workspace/release/snapshot directories and large project roots. Keep a parent total as a subtotal, never as another additive line beside its children. Size differences across separate scans can reflect concurrent writes or shared hardlinks; retain an unclassified remainder instead of inventing a category. If `df` materially exceeds `du`, investigate filesystem overhead, inaccessible paths and deleted-but-open files before attributing the gap.

## 3. Explain Docker by storage layer

Run `docker system df` and `docker system df -v`. Report separately:

- Images: repository/tag, associated container count, shared and unique sizes.
- Containers: running versus stopped, writable-layer size and recognizable role.
- Volumes: size, links and verified purpose.
- Build cache: its own reported size, not every unnamed image.

Inspect only necessary `docker inspect --format` fields such as mounts, image identity and state; avoid dumping environment variables or credentials. Include host bind mounts as host storage, not as named Docker volumes.

Do not sum full image sizes: layers are shared. Do not interpret `RECLAIMABLE` as `dangling`, nor promise that ordinary image pruning recovers the displayed total. Unnamed images can still back stopped containers. An unattached volume can contain valuable persistent data; identify it before any deletion proposal. Distinguish failed-build leftovers from intentionally stopped applications.

## 4. Classify caches and project directories

| Class | Verification before cleanup recommendation |
|---|---|
| pip/uv and npm download caches | Separate downloaded packages from installed environments; note re-download cost and check concurrent installations. |
| npm `_npx` | Identify commands using these installed tool environments; do not describe all of `.npm` as download cache. |
| Browser caches | Identify Playwright/Puppeteer/Camoufox consumers; these directories may contain the executable browser itself. |
| Model caches | List model directory names and sizes, then verify service/config references; Hugging Face weights can be live inference assets. |
| Project dependencies | Separate source and user assets from reproducible `node_modules` or environments; confirm manifests and runtime consumers. |
| Temporary-looking databases | Inspect file metadata, read-only schema, provenance and references without exposing records; no open handle is not proof of abandonment. |
| Snapshots/releases/backups | Identify rollback requirements and retention ownership; preserve a known usable recovery path. |

Do not copy a large database merely to inspect its schema; use SQLite read-only mode and bounded metadata queries. Do not infer model usefulness solely from its name or an old memory. Moving files to another directory on the same filesystem does not reclaim disk space.

## 5. Present an actionable, honest result

Use a short table: component or path, purpose, measured size, status, removal consequence. Give expandable topical detail when asked: Docker services and leftovers; cache types and model names; actual named projects. Mark inferred purposes and unknown consumers explicitly.

Rank candidates by expected savings as a share of occupied storage and operational risk. Separate measured candidate size from confirmed reclaimable bytes; do not count shared layers twice. Preserve canonical sessions, PostgreSQL/Qdrant data, needed browser assets and unreviewed workspaces by default. State that no deletion occurred.

After explicit cleanup authorization, restrict actions to the approved candidates and verify filesystem usage and affected services afterward; report actual recovered bytes rather than repeating the pre-cleanup estimate.
