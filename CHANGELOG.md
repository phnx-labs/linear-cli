# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.1]: https://github.com/phnx-labs/linear-cli/releases/tag/v0.1.1
[0.1.0]: https://github.com/phnx-labs/linear-cli/releases/tag/v0.1.0
