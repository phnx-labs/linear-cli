# Security Policy

## Reporting a vulnerability

Email **security@phnx.so** with the details. Please include:

- A description of the vulnerability and how to reproduce it
- The version of `linear-cli` you tested against (`linear --version`)
- Whether you'd like credit in the fix announcement

We aim to respond within 72 hours. Please don't open public GitHub issues for security
problems — give us a chance to ship a fix first.

## Supported versions

Only the latest minor release receives security fixes.

| Version | Supported |
|---------|-----------|
| 0.11.x  | Yes       |
| < 0.11  | No        |

## How linear-cli handles your API key

`linear-cli` resolves the API key in this order:

1. Config file — `~/.linear-cli/config.json` (mode `0600`, readable only by your user)
2. Environment variable — `LINEAR_API_KEY`
3. macOS Keychain — generic password under service `linear-api-key`

The config file is the default `linear setup` writes to. The env var and Keychain
paths exist so you can avoid storing the key on disk in plaintext if you'd rather
not.

A few tradeoffs to know:

- **Config file**: explicit `0600` permissions, but the key sits on disk. Rotate
  by re-running `linear setup --api-key <new-key>` (overwrites in place).
- **Env var**: convenient, but env vars leak through `ps`, `/proc/<pid>/environ`,
  and any child process you spawn. Don't put `LINEAR_API_KEY=...` in `.zshrc`
  or `.bashrc` — load it per-shell from a secrets manager (e.g. `pass`,
  `1password-cli`, `op read`) so it isn't sitting in your dotfiles or history.
- **Keychain (macOS)**: most paranoid. Store with
  `security add-generic-password -a "$USER" -s linear-api-key -w <key>` and
  `linear-cli` will pick it up if the config and env are both empty.

## Scope of API key access

`linear setup` asks for a Linear API key with **Full access**. The key can:

- Read all issues and projects in workspaces you belong to
- Create, update, and comment on issues
- Upload file attachments

`linear-cli` itself never reads issues outside the team you configure with `setup`,
but the key permissions allow more — if you lose control of the file, rotate the key
at [linear.app/settings/account/security](https://linear.app/settings/account/security).

## What we won't do

- We won't add telemetry. The CLI talks to `api.linear.app` and nowhere else.
- We won't auto-update. You control when to pull a new `linear` binary.
- We won't accept code from third-party packages. Stdlib only — easier to audit.
