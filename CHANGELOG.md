# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.19.1] - 2026-08-14

### Fixed

- **Windows: the CLI ran at all.** `import fcntl` sat at module scope, so every
  command — not just `queue` — died with `ModuleNotFoundError` on Windows from
  v0.18.0 onward. `fcntl` and `msvcrt` are both optional imports now, and the
  drain lock dispatches per platform: `fcntl.flock` on POSIX,
  `msvcrt.locking` on Windows.
- Windows `LK_LOCK` gives up after ~10s where `flock`'s `LOCK_EX` waits
  forever; `blocking=True` retries instead of reporting the timeout as "another
  drain holds the lock".
- A real I/O error during a blocking lock (bad fd, invalid argument) is raised
  instead of retried forever. Only documented contention codes retry.

## [0.19.0] - 2026-08-14

### Added

- **`linear projects update --priority`** — set a project's priority
  (`urgent|high|medium|low|none`), the same names `--priority` already takes on
  issues. Previously the only way to change a project's priority from the CLI
  was a raw `projectUpdate` GraphQL call.
- **Priority is now readable.** `linear projects` prints a Priority column and
  `linear projects <name>` prints a `Priority:` line, so a change made with
  `--priority` can be confirmed without opening Linear.

## [0.18.0] - 2026-08-09

### Added

- **`linear queue` / `linear queue list` / `linear queue drain`** — durable
  local queue for closes that cannot be written immediately (RUSH-2307).
  `linear update <id> --done --proof ...` persists the intent before
  attempting the API; on a Linear rate limit (429) or transient error the
  intent is retained in `~/.linear-cli/queue/` and retried later.
  `linear queue drain` applies pending closes with exponential backoff;
  `linear queue drain --once` applies a single due intent; `linear queue
  drain --dry-run` previews them. The next `linear update --done` also
  drains automatically.
- **Concurrent drain safety.** `queue_drain_lock` (`fcntl.flock` on
  `~/.linear-cli/queue/.drain.lock`) serializes drains on one machine so two
  processes cannot double-apply or corrupt intents.
- **Retry-After honored.** `gql` surfaces HTTP `Retry-After` in GraphQL error
  extensions; drain prefers that delay over exponential backoff (still
  capped).
- **Idempotent queued closes.** Duplicate intents for the same ticket collapse
  to the latest proof/comment. A drain that finds the issue already in the
  desired state removes the intent without re-posting proof.
- **Bounded queue growth.** `MAX_QUEUE_SIZE` caps the number of distinct
  intents; new intents are rejected when full, but existing intents can still
  be updated. `MAX_QUEUE_ATTEMPTS` limits retries so stuck items do not linger
  forever.

### Changed

- `gql` surfaces HTTP status codes (and Retry-After) in GraphQL error
  extensions so callers can distinguish rate limits (429) and transient
  errors from permanent failures.

### Docs

- README and `skill.md` document the queue surface and a rate-limit runbook
  for agents (close batches with queue, never tight-loop).

## [0.17.0] - 2026-08-06

### Added

- **`linear projects update <name|id>`** — set project description, name, lead,
  start/target dates, and state. Resolves the project strictly (mistyped name
  aborts). `--state` accepts a status type (`backlog` / `planned` / `started` /
  `paused` / `completed` / `canceled`) or a workspace status name; `--lead` /
  `--start` / `--target` accept `none` to clear. `--description-file` reads a
  multi-line body (or `-` for stdin).
- **`linear initiatives`** — workspace initiatives for agent workflows:
  list / show / create / update / link / unlink / archive. `link` and `unlink`
  attach projects via Linear's `initiativeToProject*` mutations; show lists
  linked projects with progress. Status values:
  `Proposed|Planned|Active|Completed|Canceled`.
- **`projects show` prints Description** when set, so a post-update check does
  not need `--json`.

### Docs

- README and skill.md cover `projects update` and the `initiatives` group.

## [0.16.1] - 2026-08-06

### Security

- **Config file is private.** `save_config` / first-write / legacy migration now
  create `~/.linear-cli` as `0700` and `config.json` as `0600` (the API key lives
  there). A pre-existing loose-mode config is re-chmod'd on every `load_config`.
- **`install.sh` fails closed on a bad download.** Pins a release tag (default
  `v0.16.1`, not floating `main`) and verifies SHA-256 before moving the binary
  into place. Override with `LINEAR_CLI_VERSION` / `LINEAR_CLI_SHA256` only when
  deliberately installing a different revision.

## [0.16.0] - 2026-08-05

### Changed

- **BREAKING: `delegate` is the only ownership model. `agent:<name>` labels no
  longer own anything.** `linear tasks --agent <name>` filtered on an
  `agent:<name>` *label* and `linear tasks --board` grouped its columns by the
  same label, so an issue delegated to Claude through Linear's own delegation UI
  did not appear in Claude's queue, and an issue merely tagged `agent:claude`
  did. Both now read the native `delegate` field; "unowned" means exactly
  `delegate` is null. A leftover `agent:*` label is inert — it is an ordinary
  label with no effect on any queue.
- **An unknown `--agent` aborts instead of listing an empty queue.** The name is
  resolved against the workspace agent roster (`linear agents`); a typo exits
  non-zero and prints the delegatable names. An unattended drain reading a silent
  empty list as "queue clear" was the failure this prevents. The *configured*
  default agent only warns: `get_agents` degrades to an empty roster on a
  transient API error, and bricking the most-used command on a users-query blip
  is worse than the typo it would catch. The filter compares delegate names
  case-insensitively either way, so the raw name still matches.
- **`--label` now composes with `--agent`.** It used to be dropped whenever an
  agent filter was active, because ownership was itself a label and the two label
  filters fought. Ownership is the delegate field now, so the two are orthogonal.

### Added

- **`linear migrate-agent-labels`** — one-time migration off the legacy labels.
  Dry run by default; `--apply` writes. It sets the delegate from a resolvable
  `agent:<name>` label, strips the migrated labels, and deletes each `agent:*`
  label once nothing carries it.

  It **never overwrites an existing delegate**. An issue already delegated to
  someone other than its label claims, or carrying two `agent:*` labels naming
  different agents, is reported as `CONFLICT` and left untouched. A label whose
  suffix is not a delegatable agent (a machine name, a workflow flag) is
  reported as `UNRESOLVED` and kept together with any sibling label on that
  issue — mixed state needs a human, and migrating half of it silently is worse.

  Decisions are per **issue**, not per label, so an issue with two `agent:*`
  labels gets exactly one write; two writes computed from the same pre-mutation
  snapshot would resurrect each other's stripped label and silently overwrite
  the delegate. A label is deleted only when nothing carries it **workspace-wide**
  and **including archived issues** — `list_team_labels` also returns
  workspace-scoped labels, so a team-scoped scan finding no hits does not mean
  unused, and Linear's `issues` connection excludes archived issues unless asked,
  so a label carried only by archived work would have looked free to delete. A
  label carried by more than 200 issues is kept outright: the gate subtracts what
  the run clears, so a truncated carrier list whose every entry happened to be
  cleared would subtract to empty and read as free. The
  dry run projects the post-migration state, so it previews the deletes the run
  would make rather than reporting every label as still carried by the very
  issues it just said it would strip.

  `--apply` exits non-zero when anything is left behind, including a failed
  `issueUpdate` or a failed `issueLabelDelete`, and the summary counters report
  writes that actually landed rather than writes that were planned. A dry run
  exits 0: it is an inspection, and reporting work-to-do as a failed migration
  left no path to a green run.

## [0.15.1] - 2026-08-05

### Fixed

- `milestone_rollup` declared its project-id variable as `String!`, but Linear's
  `issues(filter: { project: { id: { eq } } })` comparator expects `ID`. On the
  live API the query errored every call, and (since the rollup returns `{}` on
  error) every milestone silently showed `(0 issues)`. Corrected to `ID!`;
  `linear projects "<name>"` and `linear milestones list "<name>"` now report real
  per-milestone progress. Added a regression test asserting the variable type.

## [0.15.0] - 2026-08-05

### Added

- **Milestone visibility.** Every issue now carries its `projectMilestone` and
  `cycle` in `ISSUE_FIELDS` — so `linear tasks` and `linear tasks <ID>` show which
  milestone an issue belongs to, and the milestone×cycle join is queryable in one
  fetch (previously the milestone was settable via `--milestone` but never shown).
- `linear tasks --milestone "<name|uuid>"` filters the queue to one milestone.
  Pair with `--project` to disambiguate a milestone name across projects.
- `linear tasks --by-milestone` groups the list by milestone with a `No milestone`
  bucket for issues matched to a project but no milestone (the "what isn't matched
  to a deliverable" surface). Each row is annotated with its cycle. Auto-on when
  `--project` scopes the list.
- **Per-milestone progress rollups.** `linear projects "<name>"` and
  `linear milestones list "<name>"` now show `(done/total done, N%)` per milestone,
  plus a `No milestone` rollup — computed from a single slim issue query per project.

### Changed

- Scoping `linear tasks` to `--project` or `--milestone` now defaults to **all
  cycles** (the whole deliverable), not just the active cycle's slice. Pass an
  explicit `--cycle` to narrow. A bare `linear tasks` still defaults to the active
  cycle.
- `linear milestones list` shows each milestone's progress rollup in place of its
  raw UUID in the human view (the id remains in `--json`).

## [0.14.0] - 2026-07-31

### Added

- `linear create --image PATH` (repeatable) uploads each image via `upload_file()`
  and embeds it as `![name](assetUrl)` in the issue description.

## [0.13.0] - 2026-07-19

### Added

- `linear inbox` is now agent-actionable:
  - **Actions:** `--read <id>` marks specific notification(s) read (repeatable);
    `--read-all` marks everything read (via `notificationUpdate` /
    `notificationMarkReadAll`).
  - **Richer `--json`:** each notification now carries the issue (`identifier`,
    `url`, `state`), the comment (`id`, `url`, `body`), the thread `parentComment`,
    and the actor — enough for an agent to follow the ticket/thread and act.
  - The plain listing prints the follow-up recipe: reply with
    `linear update <ID> --comment "..."`, dismiss with `linear inbox --read <id>`.

## [0.12.0] - 2026-07-18

### Added

- `linear inbox` — show your Linear inbox (notifications): comments, mentions,
  assignments, and status changes on issues you follow. Unread only by default;
  `--all` includes already-read, `--limit N` bounds the fetch, `--json` for raw
  output. Backed by the GraphQL `notifications` query — no browser needed.

## [0.11.1] - 2026-07-17

### Documentation

- Add arcade-style README diagrams for the task lifecycle, the human/agent flow,
  the zero-dependency / zero-supply-chain differentiator, and the comparison
  scoreboard. `assets/flow.svg` upgraded to match.

## [0.11.0] - 2026-07-15

### Removed

- `linear cycles delete`. It mapped to Linear's `cycleArchive`, which discards a
  cycle's sprint history (issues, velocity, the numbered slot) — a destructive,
  rarely-needed op that doesn't belong in an agent-facing CLI. Cycles are now
  list/create/update only. Label/milestone/project deletes are unaffected.

## [0.10.1] - 2026-07-15

### Fixed

- Cycle display for **numbered (nameless) cycles**. Linear's auto-numbered
  cycles carry `name: null` and only a `number`, but every display site read
  `cycle.name` — so a ticket that *was* in the active cycle rendered as `None`
  (`tasks <id>`) or `no cycle` (`create`/`update` confirms), making cycle
  assignment look broken when the write had actually succeeded. All cycle
  selections now request `number` and render through a single `cycle_label()`
  helper (`name`, else `Cycle {number}`, else `no cycle`); named cycles are
  unchanged. `tasks --cycle active` headers now read `Cycle 20` instead of the
  generic `Active cycle`.

## [0.10.0] - 2026-07-13

### Added

- `linear tasks --project NAME|UUID` — scope the task list to one project.
  Resolution is strict: an unknown project aborts with close-match suggestions
  instead of silently dropping the filter and returning the whole team queue
  (unattended consumers act on whatever this lists).

## [0.9.0] - 2026-07-07

Brings the human side to parity with the agent side: humans are assignable by
name just as agents are delegatable by name, and `users` no longer buries the
two people among the app users.

### Changed
- `users` now **groups** its output into **Humans** (assign with `--assign`) and
  **Agents** (delegate with `--delegate`), using Linear's `app` user flag — the
  same flag `agents` uses. No more mixing real people with OAuth app users.
  `--json` still emits the flat list, now including the `app` field per user.
- `--assign` (on `create` and `update`) accepts a **human's name or displayName**
  (case-insensitive), not just an email — so `--assign bisma` works like
  `--delegate claude`. Email and `none` still work. Agents (app users) are
  excluded from name resolution on purpose: an unmatched name warns and points at
  `linear users`, steering agent hand-offs to `--delegate`.

## [0.8.0] - 2026-07-07

Trims the issue surface to what this workspace actually uses, and discourages
casual issue nesting. The model stays lean: task · project · milestone · cycle ·
label · status · priority · assignee/delegate.

### Removed
- `--estimate` on `create` and `update` (and the Estimate line in issue detail).
  Story-point estimation isn't used here, so the flag was pure ceremony — it's
  gone from the code, not just hidden. A stray `estimate` key in a `--from-file`
  bulk line is now silently ignored rather than sent.

### Changed
- `--parent` (sub-issues) now prints a **non-blocking tip** to stderr when it
  nests an issue ("prefer a top-level issue under a project/milestone unless you
  truly need it"). It's a nudge, not a prompt — bulk (`--from-file`) and agent
  runs stay unblocked, and the parent is still set.

## [0.7.0] - 2026-07-07

Makes the CLI own the full project lifecycle and adds milestone management, so a
workspace can be reorganized entirely from the shell instead of the web UI. Also
closes a silent-failure footgun where a mistyped `--project` no-op'd every issue
in a batch while reporting success.

### Added
- `projects create --name <name> [--description ...] [--lead <email>]
  [--start YYYY-MM-DD] [--target YYYY-MM-DD]` — create a project on the current
  team (`projectCreate`). Prints the new project's id and URL.
- `projects archive|delete <name|id>` — remove a project (`projectDelete`; moves
  it to the workspace trash, recoverable in Linear's UI). Linear exposes no
  distinct project-archive mutation, so both verbs are the same operation.
- `projects show <name|id>` — explicit detail view. Bare `projects <name>` still
  works (shorthand for `show`). Accepts a **project id** and prefers an **exact
  name match** over substring, so `Rush` stays addressable once `Rush App` /
  `Rush CLI` exist. Detail now also shows the issue count, start date, and id.
- `milestones` command — `list <project>`, `create --project --name [--target]
  [--description]`, `move <milestone> --to <project> [--from <project>]`,
  `set-target-date <milestone> <YYYY-MM-DD|none> [--project]`, and
  `delete <milestone> [--project]` (`projectMilestone{Create,Update,Delete}`).
  Setting a milestone's target date from the CLI is reliable where the web
  date-picker is not.
- `projects` list now shows a per-project **issue count** (from `scope`), so a
  bulk backfill can be verified without aggregating `tasks --json`.

### Fixed
- A named `--project` / `--milestone` that doesn't resolve is now a **hard error
  with close-match suggestions**, not a warn-and-skip on a success exit. `update`
  resolves the project/milestone **once, up front**; an unknown name aborts the
  whole run (non-zero) before any issue is touched, instead of silently no-op'ing
  every ticket in a batch while reporting success. Resolving once also removes a
  per-issue project lookup on bulk updates.

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
