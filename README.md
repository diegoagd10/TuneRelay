# TuneRelay

Turn "I like this song" on YouTube into a correctly tagged track in Navidrome:
press **Alt+Shift+M** in Brave/Chrome, review the proposed metadata in the
Omarchy bar, confirm, and the song lands in the Navidrome library on `svc-02`.

## How it fits together

- `extension/`: a Manifest V3 extension. Alt+Shift+M (or the toolbar icon)
  sends the tab URL to the native messaging host.
- `tunerelay-host`: the native messaging host. It normalises the URL (one
  video, no playlists), rejects duplicates, and downloads M4A audio, info JSON
  and thumbnail into `~/.tunerelay/inbox/<id>/` with OSD progress.
- `tunerelay daemon` (systemd user service): builds the default proposal from
  the YouTube data, asks `codex exec` for up to three sourced proposals, then
  delivers confirmed songs: it writes the tags, copies the file with rsync over
  SSH (LAN first, then Tailscale), verifies the copy, and triggers a Navidrome
  scan.
- `tunerelay` CLI: every action as a command with JSON output (`status`,
  `watch`, `list`, `show`, `select`, `edit`, `cover`, `preview`, `confirm`,
  `discard`, `replace`, `retry`, `history`). Run `tunerelay --help`.
- `shell-plugin/dagd.tunerelay/`: the Omarchy bar icon (review count, busy
  indicator) and the Review / Queue / History window. It only calls the CLI.

State lives in `~/.tunerelay/tunerelay.db` (SQLite). Server settings live in
`~/.tunerelay/config.toml`, which is created with comments on first run.

## Install

```sh
./install.sh
```

Then follow the printed steps: load `extension/` unpacked once, add the
widget to the bar, and fill in `[delivery]` and `[scan]` in the config.

## Develop

```sh
uv sync
uv run pytest      # end-to-end tests against fakes in tests/fakes/
uv run check       # quality gate: lock, ruff, format, pyright, deptry, pip-audit, tests (coverage >= 95%)
```

Tests drive the real `tunerelay` / `tunerelay-host` executables. yt-dlp,
Codex, ssh/rsync, notify-send, the OSD and `pass` are replaced by the fake
executables in `tests/fakes/`, selected through `config.toml`.

YouTube's Terms of Service may forbid downloading audio. TuneRelay is meant
for personal use, and the user has accepted that.
