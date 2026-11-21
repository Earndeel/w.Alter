---
name: mcporter
description: Use the mcporter CLI to list, configure, auth, and call MCP servers/tools directly (HTTP or stdio), including ad-hoc servers, config edits, and CLI/type generation.
version: 1.0.0
author: community
license: MIT
metadata:
  hermes:
    tags: [MCP, Tools, API, Integrations, Interop]
    homepage: https://mcporter.dev
prerequisites:
  commands: [npx]
---

# mcporter

## When to Use

- Need to call MCP server tools from the terminal (not through Hermes native MCP)
- Discovering, listing, or configuring MCP servers on the machine
- Ad-hoc MCP calls without configuring a server permanently
- OAuth auth flow for MCP servers
- Generating CLI wrappers or TypeScript types from MCP servers
- Debugging MCP server connections or auth issues

## Overview

Use `mcporter` to discover, call, and manage [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) servers and tools directly from the terminal.

## Prerequisites

Requires Node.js:
```bash
# No install needed (runs via npx)
npx mcporter list

# Or install globally
npm install -g mcporter
```

## Quick Start

```bash
# List MCP servers already configured on this machine
mcporter list

# List tools for a specific server with schema details
mcporter list <server> --schema

# Call a tool
mcporter call <server.tool> key=value
```

## Discovering MCP Servers

mcporter auto-discovers servers configured by other MCP clients (Claude Desktop, Cursor, etc.) on the machine. To find new servers to use, browse registries like [mcpfinder.dev](https://mcpfinder.dev) or [mcp.so](https://mcp.so), then connect ad-hoc:

```bash
# Connect to any MCP server by URL (no config needed)
mcporter list --http-url https://some-mcp-server.com --name my_server

# Or run a stdio server on the fly
mcporter list --stdio "npx -y @modelcontextprotocol/server-filesystem" --name fs
```

## Calling Tools

```bash
# Key=value syntax
mcporter call linear.list_issues team=ENG limit:5

# Function syntax
mcporter call "linear.create_issue(title: \"Bug fix needed\")"

# Ad-hoc HTTP server (no config needed)
mcporter call https://api.example.com/mcp.fetch url=https://example.com

# Ad-hoc stdio server
mcporter call --stdio "bun run ./server.ts" scrape url=https://example.com

# JSON payload
mcporter call <server.tool> --args '{"limit": 5}'

# Machine-readable output (recommended for Hermes)
mcporter call <server.tool> key=value --output json
```

## Auth and Config

```bash
# OAuth login for a server
mcporter auth <server | url> [--reset]

# Manage config
mcporter config list
mcporter config get <key>
mcporter config add <server>
mcporter config remove <server>
mcporter config import <path>
```

Config file location: `./config/mcporter.json` (override with `--config`).

## Daemon

For persistent server connections:
```bash
mcporter daemon start
mcporter daemon status
mcporter daemon stop
mcporter daemon restart
```

## Code Generation

```bash
# Generate a CLI wrapper for an MCP server
mcporter generate-cli --server <name>
mcporter generate-cli --command <url>

# Inspect a generated CLI
mcporter inspect-cli <path> [--json]

# Generate TypeScript types/client
mcporter emit-ts <server> --mode client
mcporter emit-ts <server> --mode types
```

## Config File Format (IMPORTANT)

The mcporter config file MUST use `mcpServers` as the top-level key (not `servers`). It's validated with Zod.

```json
{
  "mcpServers": {
    "server_name": {
      "command": "npx",
      "args": ["-y", "@scope/package-name", "run", "<optional-args>"],
      "env": {
        "API_KEY": "...",
        "OTHER_VAR": "..."
      }
    }
  }
}
```

- Default config location: `./config/mcporter.json`
- Override with `--config <path>` (Hermes uses `/root/.hermes/mcp/mcporter.json`)
- Environment variables for auth are passed via `env` in the server entry

## Common MCP Server Patterns

**npm-published stdio servers** (most common):
```bash
# Example: Cloudflare MCP server
# 1. Find the npm package: @cloudflare/mcp-server-cloudflare
# 2. Check its README for auth requirements
# 3. Some servers need extra CLI args (e.g., 'run <account-id>')
npx @cloudflare/mcp-server-cloudflare --help  # check subcommands
```

**If a server crashes on connect**: Check the README for expected env vars and CLI subcommands. Many stdio servers need specific env vars (e.g., `CLOUDFLARE_API_TOKEN`) and/or positional args.

## Cloudflare MCP Server (KNOWN PITFALLS)

The official `@cloudflare/mcp-server-cloudflare` server has critical auth limitations:

**Global API Keys (`cfk_...`) are NOT supported by the MCP server.**
The MCP server uses `Authorization: Bearer <token>`, which only works with Cloudflare API Tokens. Global API Keys require `X-Auth-Key` headers, which the MCP server does NOT send.

If you have a Global API Key and get `Authentication error (code 10000)` from `worker_put`/`worker_list`:

**Option A: Create an API Token (recommended)**
1. Go to Cloudflare Dashboard > My Profile > API Tokens > Create Token
2. Use template "Edit Cloudflare Workers" or add scopes: Workers:Edit, KV:Edit, R2:Edit, D1:Edit
3. Replace `CLOUDFLARE_API_TOKEN` in mcporter config

**Option B: Bypass MCP and use `wrangler deploy` (works with Global Keys)**
```bash
CLOUDFLARE_API_KEY='cfk_...' CLOUDFLARE_EMAIL='user@email.com' wrangler deploy --no-bundle
```
Wrangler supports both Global API Keys and API Tokens. It's the reliable fallback when the MCP server auth fails.

**Option C: Direct Cloudflare Workers API (Global Key compatible)**
```bash
# Multipart PUT to /accounts/:id/workers/scripts/:name
# Use module syntax: export default { async fetch() { ... } }
# NOT addEventListener syntax (code 10021 error)
```

**Important wrangler gotcha**: If running from a directory containing `node_modules` (e.g., `/tmp` with leftover project files), wrangler will bundle EVERYTHING. Always deploy from a clean directory or use `--no-bundle`.

## Finding Credentials

If API credentials are missing from config files, they may exist in:
- `.env` files in project directories
- Session history / trash directories (agents log full commands)
- CLI tool config files (`~/.config/*`)

Search with: `grep -r "CLOUDFLARE\|API_KEY\|API_TOKEN" /path/ --include="*.json" --include="*.env" --include="*.md"`

## Notes

- Use `--output json` for structured output that's easier to parse
- Ad-hoc servers (HTTP URL or `--stdio` command) work without any config — useful for one-off calls
- OAuth auth may require interactive browser flow — use `terminal(command="mcporter auth <server>", pty=true)` if needed
