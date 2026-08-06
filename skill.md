---
name: linear
description: Interact with Linear via the linear-cli. Query your work queue, pick up tasks, report progress, close issues with proof.
---

# linear-cli skill

You have access to the `linear` CLI — a Linear task manager built for AI agents. Config lives at `~/.linear-cli/config.json`. Team and API key are pre-configured via `linear setup`.

## Core workflow

```
linear tasks                          # your assigned queue in the active cycle
linear tasks --board                  # whole team board, grouped by delegate
linear tasks ANT-42                    # detail view for one issue
linear update ANT-42 --pickup          # move to In Progress
linear update ANT-42 --comment "..."    # drop a progress note
linear update ANT-42 --done --proof <url-or-file> --proof "deployed at X"
linear create "Title" --label foo --priority high --description "..."
linear cycles                         # list cycles
linear projects                       # list projects + issue counts (detail: `linear projects "Name"`)
linear milestones list "Name"         # a project's milestones
linear labels                         # list available labels
linear users                          # humans (--assign) + agents (--delegate), grouped
linear agents                         # agent members you can --delegate to (auto-detected)
linear states                         # the team's workflow states (valid --status values)
```

## Filters

Lists are fully paginated — `linear tasks` returns the *whole* cycle/team, not a
truncated first page. Always search before creating, to avoid duplicates.

```
linear tasks --status todo         # backlog | todo | progress | done | open
linear tasks --label security      # by any label
linear tasks --cycle active        # active (default) | next | all | none/backlog
linear tasks --cycle all           # whole team: every cycle + backlog
linear tasks --cycle none          # backlog only (issues in no cycle)
linear tasks --cycle "Q2W11"       # a specific cycle by name, number, or id
linear tasks --since 2026-06-01    # only issues created on/after a date
linear tasks --assignee me         # by assignee: me | none | someone@x.com
linear tasks --project "Rush App"  # scope to one project (name or UUID; strict)
linear tasks --query "auth"        # search title + description
linear tasks --json                # machine-readable
linear tasks --agent claude        # issues delegated to one agent (see: linear agents)
linear tasks --all                 # every issue, whoever it is delegated to
```

If unsure of a status name, run `linear states` instead of guessing.

**Ownership is the `delegate` field, and nothing else.** With `agent` set in
config, `linear tasks` shows what is delegated to you plus what is delegated to
nobody; `--agent <name>` shows one agent's queue; `--board` groups columns by
delegate. Labels never confer ownership — `--label` is an ordinary filter that
composes with `--agent`. An unknown `--agent` exits non-zero instead of printing
an empty queue.

## Editing existing issues

Everything you can set on `create` can be changed on `update` with the same flag. Examples:

```
linear update ANT-42 --priority urgent --assign bisma        # human by name or email
linear update ANT-42 --title "Renamed" --description "Rewritten body"
linear update ANT-42 --project "Phoenix" --milestone "v1.0"
linear update ANT-42 --parent ANT-10             # nest under a parent (prints a tip)
linear update ANT-42 --blocked-by ANT-7 --blocks ANT-9            # relations
linear update ANT-42 --relates ANT-5                              # non-blocking link
linear update ANT-42 --delegate codex                             # hand to an agent (see: linear agents)
linear update ANT-42 --project none                               # detach
```

Relations are read back in the detail view (`linear tasks ANT-42`) as
Blocks / Blocked by / Related to. Use `--blocked-by` before picking up a task to
record what it depends on.

## Bulk update — one change, many tickets

`update` accepts multiple identifiers, or reads them from stdin (xargs-style).
Single-ticket invocations are unchanged; with 2+ ids you get `[i/n]` progress and
an error roll-up at the end (one bad ticket never aborts the batch).

```
linear update ANT-1 ANT-2 ANT-3 --cycle none          # pull several out of the cycle
linear update ANT-1 ANT-2 --label triage --priority high
linear tasks --cycle all --json | jq -r '.issues[].identifier' \
  | linear update --stdin --comment "swept into triage"
```

## Managing cycles and labels

CRUD from the shell instead of dropping to raw GraphQL. Both resolve the target
by fuzzy name, number, or UUID. Cycles are list/create/update only — there is no
`cycles delete`, because archiving a cycle discards its sprint history. Labels
support `delete`.

```
linear cycles --ids                                   # list with UUIDs
linear cycles create --name "Jul W1" --starts 2026-07-01 --ends 2026-07-07
linear cycles update "Jul W1" --name "Jul Week 1"     # or --starts/--ends

linear labels create triage --color "#ff8800" --description "needs triage"
linear labels update triage --name needs-triage       # or --color/--description
linear labels delete needs-triage
```

## Managing projects and milestones

Own the whole project lifecycle from the shell. `projects <name>` (or `show`)
takes an **exact name or id**; a mistyped `--project` on `create`/`update` is a
hard error (with suggestions), never a silent no-op.

```
linear projects                                       # list + progress + issue count
linear projects "Rush App"                            # detail: exact name or id
linear projects create --name "Rush App" --lead you@co.com --target 2026-09-30
linear projects archive "Old Project"                 # remove (moves to Linear trash)

linear milestones list "Rush App"
linear milestones create --project "Rush App" --name "Alpha 25" --target 2026-08-15
linear milestones set-target-date "Alpha 25" 2026-08-20 --project "Rush App"
linear milestones move "Alpha 25" --to "Rush CLI" --from "Rush App"
linear milestones delete "Alpha 25" --project "Rush CLI"
```

## Creating issues — what's required

Only one thing: a title OR a description. Everything else has a sensible default.

```
linear create "Fix auth bug"                          # minimum
linear create --description "Long paragraph..."       # title derived from first line/sentence
linear create --description-file plan.md              # multi-paragraph markdown
echo "..." | linear create --description-file -       # stdin
linear create "Sub-task" --parent ANT-42             # nested; prints a tip nudging a flat issue
linear create "Item" --project "Phoenix" --milestone "v1.0"
linear create --from-file plan.jsonl                  # bulk: one issue per JSON line
```

Bulk output is tab-separated for easy parsing:
```
OK    ANT-42  Fix auth
ERROR  -      Other       project 'Foo' not found
```
Bad lines don't stop the run.

## Multi-team workspaces

```
linear --team ENG tasks       # one-shot override, doesn't mutate config
linear --team OPS create ...
```

## Output mode for agent use

Always prefer `--json` when parsing output programmatically:

```
linear tasks --json | jq '.issues[] | {id: .identifier, title, state: .state.name}'
```

## Assignee-as-queue model

- `linear tasks` without flags returns issues assigned to the identity that owns the API key.
- If `cfg.agent` is set at setup time (e.g. `claude`, `codex`), `linear tasks` additionally filters by a matching label — the "agent lane" pattern. Override with `--all`.
- Default scope is the active cycle. Use `--cycle all` to search the whole team (e.g. before creating, to avoid duplicates), `--cycle none` for the backlog, or `--assignee <email>` to query someone else's queue.
- `linear update <id> --pickup` = claim the task. Follow with `--done --proof` when shipped.

## Proof-of-completion

`--proof` is repeatable and accepts:
- File paths (uploaded to Linear as attachments)
- URLs (rendered as links)
- Plain text (appended as a line)

Use it on `update --done` so reviewers see evidence without digging.

## Common mistakes

- Don't call the Linear GraphQL API directly — the CLI handles auth, uploads, cycle math, and state resolution.
- Don't hand-edit `~/.linear-cli/config.json` — use `linear setup` to re-configure.
- If you see `Error: Invalid scope: read required`, the API key was created write-only. Regenerate it with Full access at linear.app/settings/account/security.
