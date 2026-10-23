---
name: docker-integration
description: Docker commands, patterns, and troubleshooting for containers, images, compose, and networking.
category: devops
---

# Docker Integration

## When to Use
- Building, running, or managing Docker containers and images
- Writing or debugging docker-compose.yml configurations
- Networking between containers, port mapping, volume mounts
- Troubleshooting container startup failures, image build issues

## Key Commands

### Containers
```bash
docker run -d --name <name> -p <host>:<container> <image>
docker ps -a                          # list all containers
docker logs -f <container>            # follow logs
docker exec -it <container> /bin/sh   # shell into container
docker rm -f <container>              # force remove
```

### Images
```bash
docker build -t <name>:<tag> .
docker images                         # list images
docker rmi <image>                    # remove image
docker system prune -a                # clean everything
```

### Compose
```bash
docker compose up -d                  # start detached
docker compose down                   # stop and remove
docker compose logs -f <service>      # follow service logs
docker compose restart <service>      # restart one service
```

### docker-compose v1 → v2 Migration
**docker-compose v1 (Python-based, `docker-compose` hyphenated) is broken on Docker 29+.** Error: `DockerException: Error while fetching server API version: Not supported URL scheme http+docker`.

Fix — install the v2 Go binary as a Docker CLI plugin:
```bash
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version  # should show "Docker Compose version v2.x.x"
```

After install: use `docker compose` (space, no hyphen) instead of `docker-compose` (hyphen). The `-f` flag works the same way: `docker compose -f docker-compose.prod.yml up -d`.

## Common Patterns

### Multi-stage build (reduce image size)
```dockerfile
FROM node:20 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
CMD ["node", "dist/index.js"]
```

### Health check
```dockerfile
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8080/health || exit 1
```

## Integrating Monorepo Workspace Packages in Docker

When a dependency is a monorepo workspace package (not published to npm, or published with a lag), you need to build from source and install manually. **Critical order of operations:**

### The Clobber Pitfall
`npm install` deletes any packages in `node_modules` that aren't in its resolved tree. If you manually extract workspace tarballs BEFORE `npm install`, they get wiped.

### Correct Sequence

```dockerfile
# 1. Base deps
RUN npm ci && npm uninstall <registry-package>

# 2. Install ALL external runtime deps (BEFORE manual placement)
RUN npm install --legacy-peer-deps \
    lodash.throttle@4.1.1 \
    jotai@2.11.0 \
    # ... all deps from the workspace package's package.json ...
    && npm cache clean --force

# 3. Copy and extract workspace tarballs (AFTER npm install)
COPY tmp/workspace-tarballs/ /tmp/tarballs/
RUN cd /tmp/tarballs && \
    mkdir -p /app/node_modules/@scope && \
    for pkg in pkg1 pkg2 pkg3; do \
        tarball=$(ls ${pkg}-*.tgz 2>/dev/null | head -1); \
        tar -xzf "$tarball" -C /tmp && \
        mv /tmp/package "/app/node_modules/@scope/${pkg}"; \
    done

# 4. Copy source (EXCLUDES node_modules via .dockerignore)
COPY frontend/ ./
```

### Discovering Hidden Internal Packages
Don't guess which packages are needed. Scan the built JS:
```bash
grep -oh '"@scope/[^"]*"' dist/prod/index.js | sort -u
```

### Tarball Structure Varies
Some tarballs extract as `./package/...`, others as `./src/...`. Check with `tar -tzf` before writing extraction loops. If the structure is wrong, `mv /tmp/package` will fail.

### Peer Dependency Conflicts
When mixing workspace packages with modern build tools (Vite 7, etc.), use `--legacy-peer-deps` and pick versions compatible with the build tool, not the workspace package.

## Pitfalls
- `docker system prune -a` removes ALL unused images, not just dangling ones
- Port conflicts: check with `lsof -i :<port>` before binding
- Volume permissions: container user may differ from host user — use `--user` or fix ownership
- Compose `depends_on` only waits for container start, not readiness — use healthchecks
- Alpine images may miss glibc — use `node:20-slim` or `python:3.11-slim` for compiled deps
- Dockerfile COPY order matters for cache — copy package files before source code
- **docker-proxy `-use-listen-fd` hang**: When Docker starts via systemd socket activation (`docker.socket` active), `docker-proxy` runs with `-use-listen-fd`. Symptom: TCP connections to published ports succeed, but HTTP/data never arrives (hangs forever). Diagnosis: `ps aux | grep docker-proxy` shows `-use-listen-fd` flag. Fix: recreate container with `--network host` to bypass docker-proxy entirely. `docker restart` does NOT fix it — must `docker rm` + `docker run --network host`.
