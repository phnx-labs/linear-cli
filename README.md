# linear-cli

A terminal Linear client built for AI agents. Query your queue, claim tasks, report progress, close with proof — all from the shell or a subagent.

Single-file Python (stdlib only). No npm, no cargo, no `@linear/sdk`. Works on macOS and Linux.

## Install

```bash
curl -sSL https://raw.githubusercontent.com/muqsitnawaz/linear-cli/main/install.sh | bash
```

Or manually:

```bash
curl -o /usr/local/bin/linear https://raw.githubusercontent.com/muqsitnawaz/linear-cli/main/linear
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

## Requirements

- Python 3.10+ (stdlib only, no pip deps)
- A Linear API key with Full access

## License

MIT.
