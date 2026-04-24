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
| 0.1.x   | Yes       |
| < 0.1   | No        |

## How linear-cli handles your API key

`linear-cli` writes its config to `~/.linear-cli/config.json` with mode `0600`
(readable only by your user). That file contains your Linear API key.

We chose a config file rather than environment variables because:

- Config files have explicit permissions; env vars leak through `ps`, `/proc/<pid>/environ`,
  and child processes you didn't intend to share with.
- An API key in your shell history or `.zshrc` is harder to rotate.

If you'd prefer Keychain or a secrets manager, please open an issue with your use case.

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
