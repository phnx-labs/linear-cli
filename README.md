# linear-cli

> Linear for you and your agents. Same queue, same CLI.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Dependencies: 0](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](#zero-dependencies-literally)
[![Supply chain: 0 attack surface](https://img.shields.io/badge/supply%20chain-0%20attack%20surface-brightgreen.svg)](#zero-supply-chain-attack-surface)
[![Single file](https://img.shields.io/badge/single%20file-43%20KB-brightgreen.svg)](./linear)
[![Team CLI](https://img.shields.io/badge/team-CLI-a3e635.svg)](#why-the-mcp-server-isnt-always-the-answer)

Issue tracking from the shell — for humans and their agents. Query your queue, claim tasks, report progress, close with proof. Works the same whether you're typing or a subagent is.

Single-file Python (stdlib only). No npm, no cargo, no `@linear/sdk`. Works on macOS and Linux.

<p align="center">
  <img src="assets/flow.svg" alt="How a Linear ticket becomes a PR: a human files the ticket and stays the assignee, an agent picks it up by lane label, ships a PR plus proof, then the human reviews. linear-cli is the contract between them." width="100%" />
</p>

<p align="center">
  <a href="https://github.com/phnx-labs/linear-cli/releases/download/v0.1.0/LinearDemo.mp4">
    <img src="https://github.com/phnx-labs/linear-cli/releases/download/v0.1.0/LinearDemo.gif" alt="linear-cli in 30 seconds: list your queue, claim a ticket with --pickup, close it with --done --proof. Click through for the MP4 with audio." width="100%" />
  </a>
  <br />
  <sub><a href="https://github.com/phnx-labs/linear-cli/releases/download/v0.1.0/LinearDemo.mp4">Watch with audio (MP4, 1.4 MB)</a></sub>
</p>

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

> **Security:** treat the API key like a password. **Do not paste it into chat with an LLM in plaintext.** Pass it from your shell env (`linear setup --api-key "$LINEAR_API_KEY"`), or let linear-cli read it from the macOS Keychain. Resolution order is: config file → `LINEAR_API_KEY` env → Keychain service `linear-api-key`.

## Usage

```bash
linear tasks                         # your queue in the active cycle
linear tasks --board                 # whole team board
linear tasks ANT-42                   # detail view
linear tasks --json | jq             # machine-readable

linear update ANT-42 --pickup         # claim (In Progress)
linear update ANT-42 --comment "..."  # progress note
linear update ANT-42 --done --proof https://pr/123 --proof "deployed"

linear create "Fix auth bug" --label security --priority high
linear cycles
```

Full help: `linear <command> --help`.

## For humans and agents

The same CLI works whether you're typing or a subagent is. Driving Linear from either shouldn't require shelling out to `@linear/sdk`, hand-rolling GraphQL, or parsing HTML.

- **Assignee-as-queue.** `linear tasks` returns what *you* own, filtered to the active cycle. No dashboards, no saved views.
- **Agent-lane labels.** Set `--agent claude` at setup and `linear tasks` filters to issues labeled for that agent. Multiple agents can share a team without stepping on each other.
- **Proof-first completion.** `--done --proof <file|url|text>` uploads attachments, records links, and appends notes in one call — so reviewers see evidence without digging.
- **JSON everywhere.** `--json` on every read command. Pipe to `jq` or hand to a subagent.

<p align="center">
  <em>Works with</em>
  <br /><br />
  <img src="assets/harnesses/anthropic.svg" alt="Claude (Anthropic)"  height="32" />
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/harnesses/openai.svg"    alt="Codex (OpenAI)"      height="32" />
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/harnesses/google.svg"    alt="Gemini (Google)"     height="32" />
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/harnesses/cursor.svg"    alt="Cursor"              height="32" />
</p>

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

### Zero supply chain attack surface

This is the boring superpower of having no dependencies.

Every notable CLI supply chain attack of the last few years — `event-stream`, `colors`/`faker`, `ua-parser-js`, `node-ipc`, the `xz` backdoor, `polyfill.io`, the dozens of [npm typosquats](https://socket.dev) caught monthly — happened through a compromised dependency, not the tool itself. linear-cli has none. The full audit surface is:

- The 1263 lines of Python in this repo (read it: [`linear`](./linear))
- Python's standard library
- Linear's own GraphQL API at `api.linear.app`

That's it. No `npm install` running 200 postinstall scripts. No transitive dependency eight layers deep that you've never heard of. No `package-lock.json` to audit, no `Cargo.lock` to chase, no Deno permissions matrix. If you trust this repo and Python's stdlib, you're done auditing.

It's probably the most boring CLI you'll ever security-review. That's the point.

### Why the MCP server isn't always the answer

Linear ships a first-party MCP server at `mcp.linear.app/mcp`. It's great for interactive chat. Less great for agents doing volume work:

- MCP injects the full tool catalog into every turn. Industry data: [40–50% of the context window](https://www.speakeasy.com/blog/how-we-reduced-token-usage-by-100x-dynamic-toolsets-v2) is consumed by tool schemas before the agent does anything. The [Linearis author cites ~13k tokens](https://zottmann.org/2025/09/03/linearis-my-linear-cli-built.html) for Linear's MCP alone. That was the explicit reason he built a CLI.
- [Benchmarks](https://onlycli.github.io/OnlyCLI/blog/mcp-token-cost-benchmark/) show CLI tools completing the same tasks ~33% more token-efficiently than equivalent MCP servers.
- `linear tasks --json` returns exactly the bytes you asked for. That's the whole point.

If you want the MCP, use it. If you want a subagent to burn through 50 tickets without blowing its context on schema chatter, use this.

## Requirements

- Python 3.9+ (ships with every macOS since 11, every Ubuntu since 20.04)
- A Linear API key with [Full access](https://linear.app/settings/account/security)

## FAQ

### Can the agent be the assignee directly, instead of routing by label?

Yes. If your agent has its own Linear account (many teams provision one seat per agent — e.g. `claude@yourcompany.com`, `codex@yourcompany.com`), run `linear setup --api-key <agent's own key>` without `--agent`. Then `linear tasks` returns tickets assigned *directly to the agent's user*. No labels, no filtering — the assignee IS the lane.

Use `--agent <label>` when you want multiple agents to share one Linear seat; skip it when each agent has its own.

### How do I rotate the API key?

Revoke the old key at [linear.app/settings/account/security](https://linear.app/settings/account/security) and run `linear setup --api-key <new-key>` again. The config file is overwritten in place.

### Does it work on Windows?

Untested. The script is plain Python + `urllib` + `subprocess`, so it should run under WSL or Git Bash. The only macOS-specific bit is the Keychain fallback in `get_api_key` (via the `security` binary) — on other platforms it silently skips, so use the env var or config file.

### Why Python instead of Go / Rust / Node?

Because every Mac and every modern Linux already ships it. Zero install, zero toolchain, zero `npm audit` churn. The tradeoff is startup isn't as fast as a compiled binary (~170 ms vs ~10 ms), but for a tool invoked a handful of times per ticket that's noise.

## License

MIT.
