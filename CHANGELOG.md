# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-07-06

Makes delegation legible: the CLI now **reads and displays** the delegate, so a
handed-off issue shows who's on it. Before this, `--delegate` was write-only —
you could hand an issue to an agent but querying it afterward only ever showed
the human assignee.

### Added
- `delegate { name }` is now requested in the list and detail queries.
- `tasks` / list rows render the delegate alongside the assignee as
  `Assignee → delegate` (e.g. `Muqsit → claude`); rows with no delegate are
  unchanged.
- `show` prints a `Delegate:` line under `Assignee:` when the issue is delegated.

## [0.5.0] - 2026-07-01

Makes the CLI aware of Linear's agent members (app users like Claude, Codex,
Kimi, …) and adds first-class delegation — the supported way to hand an issue to
an agent (Linear silently ignores an app user in `assigneeId`).

### Added
- `agents` — list the workspace's agent members, auto-detected via the Linear
  `app` user flag. The roster is cached in config and auto-refreshed every 6h;
  `agents --refresh` forces an immediate re-fetch after installing/removing an
  agent app. `--json` for scripting.
- `update --delegate <name>` and `create --delegate <name>` — delegate an issue
  to an agent by name (case-insensitive, e.g. `--delegate claude`), or `none` to
  clear. Resolves the name against the cached roster (refreshing once on a miss),
  then sets `delegateId`. The human stays the assignee; the agent becomes the
  delegate.

### Changed
- Docs and the hero flow diagram (`assets/flow.svg`) now teach delegation instead
  of the retired `agent:*` lane-label hand-off — `--label agent:foo` examples are
  replaced with `--delegate <name>`; the diagram shows the ticket carrying both an
  assignee (human) and a delegate (agent).

### Notes
- Agent roster caching reuses the volatile-config guard, so `--team` overrides
  never persist another workspace's roster.

## [0.4.0] - 2026-06-23

Finishes the shell-native management story for cycles and labels, completes the
pagination sweep, and makes `update` a batch tool. Closes the remaining open
issues (#3, #4, #5, #6, #7, #8).

### Added
- `cycles create|update|delete` — manage cycles from the shell instead of
  dropping to raw GraphQL (`cycleCreate` / `cycleUpdate` / `cycleArchive`).
  `cycles --ids` (and `--json`) surface the cycle UUIDs. (#4)
- `labels create|update|delete` — label CRUD via `issueLabelCreate` /
  `issueLabelUpdate` / `issueLabelDelete`, with fuzzy id-or-name resolution, for
  cleaning up accidental/one-off labels. (#5)
- `tasks --cycle <name|id>` — scope the list to any specific cycle by fuzzy name,
  number, or UUID (on top of the existing `active|next|all|none`). `backlog` is
  now an accepted alias for `none`. (#6)
- `tasks --since YYYY-MM-DD` — floor the list to issues created on/after a date. (#6)
- Bulk `update`: pass multiple identifiers (`update RUSH-1 RUSH-2 --cycle none`)
  or pipe them with `--stdin` (`... | linear update --stdin --label x`). Per-issue
  `[i/n]` progress, errors rolled up at the end (one bad ticket never aborts the
  batch), single-ticket output unchanged. (#7)

### Fixed
- `tasks --board` no longer queries the non-existent `team.nextCycle` field —
  `--board --cycle next` (and every board view) now resolves the cycle the same
  way as the list view, so it returns results instead of a GraphQL error. (#3)
- `tasks --board` is now fully paginated and accepts all cycle scopes; it
  previously hit the old single-page `activeCycle.issues` path and silently
  capped at 50. (#8)
- Pagination now also covers `cycles`, `labels`, `users`, and `projects` (and
  the label lookups used by `update`/`create`), via a shared `paginate_connection`
  helper — no list silently truncates at Linear's default page size. (#8)

## [0.3.1] - 2026-06-24

### Fixed
- Detail view now renders symmetric relations (`related`, `duplicate`) from the
  inverse side too — previously only `blocks` inverted to "Blocked by", so a
  `related`/`duplicate` link was invisible from the issue that didn't author it.
  Found while live-testing relation writes against a real team.

## [0.3.0] - 2026-06-24

Closes the load-bearing read gaps for agent workflows. The headline is
pagination: lists no longer silently truncate at Linear's 50-issue page cap —
on a real cycle this surfaced 137 tasks where the old code showed 50, the exact
cause of "search before you create" missing existing tickets and filing
duplicates.

### Added
- Full pagination on every issue list (`tasks`, `--query`, `--board`) — follows
  `pageInfo` to the end instead of stopping at the first 50 results
- `tasks --cycle all` (whole team: every cycle + backlog) and `--cycle none`
  (backlog only) — previously listing was locked to the active/next cycle
- `tasks --assignee me|none|<email>` — filter by real assignee, not just the
  `agent:` label lane
- `linear states` — list the team's workflow states, so agents stop guessing
  status names and learning they were wrong only when a mutation fails
- `update --blocks`, `--blocked-by`, `--relates` (repeatable) — create issue
  relations via `issueRelationCreate`
- Detail view (`tasks ANT-N`) now shows relations (Blocks / Blocked by / Related
  to / Duplicate of), plus project, cycle, parent, url, estimate, and due date

### Changed
- `tasks --json` shape: `{ scope, cycle, count, issues }` (the `issues` array is
  unchanged; `cycle` is null for `all`/`none` scopes)
- Detail-view query enriched — `--json` no longer drops project/cycle/parent/
  url/estimate/dueDate/relations

## [0.2.0] - 2026-06-07

Broad expansion of the create/update surface to cover the fields agents actually
need — projects, milestones, sub-issues, story points, reassignment — plus
discovery commands and bulk create. Symmetry fix: every field settable on
`create` is now changeable on `update` with the same flag.

### Added
- `--project NAME|ID` and `--milestone NAME` on `create` and `update`. Name resolution with smart-pick on ambiguity (most-recently-updated match) — no flag dance required
- `--parent ANT-N` on `create` and `update` for sub-issues; `none` on update detaches
- `--estimate N` on `create` and `update` (story points)
- `--title` and `--description` on `update` (rename / replace body)
- `--description-file PATH` on `create` and `update`, with `-` for stdin (multi-paragraph markdown without shell-escape pain)
- `--unlabel NAME` on `update` (repeatable) — mirrors `--label` add semantics for clean agent hand-off
- `--priority` and `--assign` on `update` (symmetry fix — both were `create`-only)
- `--query "text"` on `tasks` — case-insensitive search across title + description; composes with all existing filters
- `--from-file plan.jsonl` on `create` — bulk creation, one JSON object per line, `-` for stdin. Continue-on-error; tab-separated output
- `--team KEY` global override (top-level flag, stateless — doesn't mutate config)
- `linear projects` — list projects in the team with status, progress, lead
- `linear projects <name>` — detail view with milestones inline
- `linear labels` — list available labels for the team
- `linear users` — list active users (for `--assign` lookup)

### Changed
- `linear create` title argument is now **optional**: if only `--description` is provided, the title is derived from its first sentence/line (markdown noise stripped, capped at 80 chars). Only true error case: neither title nor description given
- `cmd_create` internally refactored: shared `_build_create_input` + `_send_issue_create` helpers used by both single and bulk paths — no duplicated resolution logic

## [0.1.2] - 2026-04-26

### Fixed
- `install.sh` error message claimed Python 3.10+ was required; the script actually works on 3.9+ (matches README, badge, comparison table, and FAQ)
- `SECURITY.md` claimed env vars were rejected as a key-resolution path; the CLI has always supported `LINEAR_API_KEY` env var and macOS Keychain. Rewrote the section to document all three paths (config / env / Keychain) with their tradeoffs

## [0.1.1] - 2026-04-24

Documentation polish on top of v0.1.0. No code changes beyond the version bump.

### Added
- Hero demo video (1080p, 17s, with audio) embedded in README, sourced from the v0.1.0 release asset
- `assets/flow.svg` — replaces the ASCII flow diagram with a dark-grid SVG showing the human-files / agent-implements / human-reviews loop
- "Zero supply chain attack surface" section in README, with matching badge
- "Works with" harness logos in README (Claude / Codex / Gemini / Cursor) under `assets/harnesses/`

### Fixed
- Replaced personal email and handle in `assets/flow.svg` with example values

## [0.1.0] - 2026-04-24

First public release.

### Added
- `linear tasks` — your queue in the active cycle (assignee-as-queue model)
- `linear tasks --board` — whole team board across cycles
- `linear tasks <ID>` — issue detail view with comments
- `linear tasks --json` — machine-readable output for piping to `jq` or subagents
- `linear update` — claim (`--pickup`), comment (`--comment`), close with proof (`--done --proof`), set status, change cycle, add labels
- `linear create` — open a new issue with priority, labels, description
- `linear cycles` — list cycles for the active team
- `linear setup` — configure API key, default team, and agent identity
- Proof-first completion: `--proof` accepts files (uploads as attachment), URLs (records as link), or text (appends as comment)
- Per-agent lane filtering via `--agent` setup flag (e.g. only see tasks labeled for `claude`)
- Auto-migration from `~/.agents/linear.json` if present
- Single-file Python distribution (~43 KB), zero third-party dependencies

[0.2.0]: https://github.com/phnx-labs/linear-cli/releases/tag/v0.2.0
[0.1.2]: https://github.com/phnx-labs/linear-cli/releases/tag/v0.1.2
[0.1.1]: https://github.com/phnx-labs/linear-cli/releases/tag/v0.1.1
[0.1.0]: https://github.com/phnx-labs/linear-cli/releases/tag/v0.1.0
