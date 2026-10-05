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

To update an existing installation:

```sh
git pull --ff-only
./install.sh
```

The installer restarts a running Omarchy shell to load the updated window.
A plugin rescan can keep old QML in memory. If the installer reports that it
could not load the window, run `omarchy restart shell` from the desktop session.

## Keyboard

The bar icon opens the TuneRelay window. For a global key, bind
`omarchy-shell shell toggle dagd.tunerelay` in `~/.config/hypr/bindings.lua`;
`install.sh` suggests a key that is still free (Super+Ctrl+M first). Two
Hyprland bindings on the same key both run, so check before adding one.

In the window, single keys act while no field has focus; a hint line at the
bottom lists them (`?` hides it). Esc leaves a field, then closes the window.

| Where   | Keys |
|---------|------|
| Anywhere | Alt+1/2/3 tabs · Ctrl+Tab / Ctrl+Shift+Tab next / previous tab · PgUp/PgDn scroll · Esc close · `?` hints |
| Review  | j/k or ↓/↑ song · 1–4 proposal · e or i edit (Tab moves between fields) · c compilation · t thumbnail cover · p preview · o YouTube · Ctrl+Enter confirm · Ctrl+Shift+Enter replace · Shift+D discard |
| Queue   | j/k or ↓/↑ scroll |
| History | j/k or ↓/↑ song · `/` search · f state filter · o or Enter YouTube · r retry |

Ctrl+Enter also works while editing a field: the field is saved first.

## Develop

```sh
uv sync
uv run pytest      # end-to-end tests against fakes in tests/fakes/
uv run check       # quality gate: lock, ruff, format, pyright, deptry, pip-audit, tests (coverage >= 95%)
```

The quality gate also enforces design decision D-10: one concrete type per
variable (no `Any`/`object`, no mixed unions, only `X | None`). The single
recorded exception is `src/tunerelay/jsondata.py`, the JSON/TOML boundary,
which may declare `Any`.

Tests drive the real `tunerelay` / `tunerelay-host` executables. yt-dlp,
Codex, ssh/rsync, notify-send, the OSD and `pass` are replaced by the fake
executables in `tests/fakes/`, selected through `config.toml`.

YouTube's Terms of Service may forbid downloading audio. TuneRelay is meant
for personal use, and the user has accepted that.
