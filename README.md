# linear-cli

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Dependencies: 0](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](#zero-dependencies-literally)
[![Single file](https://img.shields.io/badge/single%20file-43%20KB-brightgreen.svg)](./linear)
[![Built for agents](https://img.shields.io/badge/built%20for-AI%20agents-8b5cf6.svg)](#built-for-ai-agents)

A terminal Linear client built for AI agents. Query your queue, claim tasks, report progress, close with proof — all from the shell or a subagent.

Single-file Python (stdlib only). No npm, no cargo, no `@linear/sdk`. Works on macOS and Linux.

## Install

```bash
curl -sSL https://raw.githubusercontent.com/phnx-labs/linear-cli/main/install.sh | bash
```

Or manually:

```bash
curl -o /usr/local/bin/linear https://raw.githubusercontent.com/phnx-labs/linear-cli/main/linear
chmod +x /usr/local/bin/linear
```

## Setup

Create a Linear API key with Full access at [linear.app/settings/account/security](https://linear.app/settings/account/security), then:

```bash
linear setup --api-key lin_api_... --agent claude
```

Config is written to `~/.linear-cli/config.json`. If you already have `~/.agents/linear.json` from an earlier setup, linear-cli auto-migrates it on first run.

## Usage

```bash
linear tasks                         # your queue in the active cycle
linear tasks --board                 # whole team board
linear tasks GR-42                   # detail view
linear tasks --json | jq             # machine-readable

linear update GR-42 --pickup         # claim (In Progress)
linear update GR-42 --comment "..."  # progress note
linear update GR-42 --done --proof https://pr/123 --proof "deployed"

linear create "Fix auth bug" --label security --priority high
linear cycles
```

Full help: `linear <command> --help`.

## Built for AI agents

linear-cli exists because driving Linear from a subagent shouldn't require shelling out to `@linear/sdk`, hand-rolling GraphQL, or parsing HTML.

- **Assignee-as-queue.** `linear tasks` returns what *you* own, filtered to the active cycle. No dashboards, no saved views.
- **Agent-lane labels.** Set `--agent claude` at setup and `linear tasks` filters to issues labeled for that agent. Multiple agents can share a team without stepping on each other.
- **Proof-first completion.** `--done --proof <file|url|text>` uploads attachments, records links, and appends notes in one call — so reviewers see evidence without digging.
- **JSON everywhere.** `--json` on every read command. Pipe to `jq` or hand to a subagent.

## Agent skill

Drop [`skill.md`](./skill.md) into your agent's skills directory (e.g. `~/.claude/skills/linear/skill.md`) to teach Claude / Codex / Gemini how to use the CLI without you explaining it every session.

## Why this one?

The Linear CLI space already has options. Here's what's different about this one, measured — not vibes.

### Zero dependencies. Literally.

```
$ grep -E '^(import|from)' linear | sort -u
from __future__ import annotations
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
import argparse
import json
import mimetypes
import os
import subprocess
import sys
```

Every symbol is in the Python standard library. No `pip install`. No `npm install`. No `cargo build`. No Deno. The whole tool is one ~43 KB file you can read top-to-bottom in an hour.

### How it compares

| Tool | Runtime | Deps | Install footprint | Last published |
|------|---------|------|-------------------|----------------|
| **linear-cli** (this) | Python 3.9+ stdlib | **0** | 43 KB, 1 file | active |
| [`@linear/cli`](https://www.npmjs.com/package/@linear/cli) (official) | Node | 0 | 5 MB npm pkg | Nov 2021 (abandoned) |
| [Linearis](https://github.com/czottmann/linearis) | Node | `@linear/sdk` + `commander` | 27 MB `node_modules` | 2025 |
| [schpet/linear-cli](https://github.com/schpet/linear-cli) | Deno | 25+ imports (cliffy, graphql-codegen, unified, valibot…) | Deno + codegen | active |
| [scmfury/linear-cli](https://github.com/feras239/linear-cli) | Node 18+ | `@linear/sdk`, commander, dotenv, picocolors | 27 MB `node_modules` | 2025 |
| [evangodon/linear-cli](https://github.com/evangodon/linear-cli) | Node | 18 deps (oclif, boxen, chalk, inquirer, marked…) | heavy | stale |
| [Finesssee/linear-cli](https://github.com/Finesssee/linear-cli) | Rust toolchain | 28 crates (tokio, reqwest, clap, keyring…) | compiled binary | active |
| Linear's hosted [MCP server](https://linear.app/docs/mcp) | remote | — | 0 local, but 13k+ tokens injected into every agent turn | active |

Numbers verified against each project's `package.json` / `Cargo.toml` / `deno.json` via the npm registry.

### Why the MCP server isn't always the answer

Linear ships a first-party MCP server at `mcp.linear.app/mcp`. It's great for interactive chat. Less great for agents doing volume work:

- MCP injects the full tool catalog into every turn. Industry data: [40–50% of the context window](https://www.speakeasy.com/blog/how-we-reduced-token-usage-by-100x-dynamic-toolsets-v2) is consumed by tool schemas before the agent does anything. The [Linearis author cites ~13k tokens](https://zottmann.org/2025/09/03/linearis-my-linear-cli-built.html) for Linear's MCP alone. That was the explicit reason he built a CLI.
- [Benchmarks](https://onlycli.github.io/OnlyCLI/blog/mcp-token-cost-benchmark/) show CLI tools completing the same tasks ~33% more token-efficiently than equivalent MCP servers.
- `linear tasks --json` returns exactly the bytes you asked for. That's the whole point.

If you want the MCP, use it. If you want a subagent to burn through 50 tickets without blowing its context on schema chatter, use this.

## Requirements

- Python 3.9+ (ships with every macOS since 11, every Ubuntu since 20.04)
- A Linear API key with [Full access](https://linear.app/settings/account/security)

## License

MIT.
