#!/bin/bash
# Install TuneRelay for the current user:
#   - the `tunerelay` and `tunerelay-host` executables (uv tool),
#   - the native messaging host manifest for Brave, Chrome and Chromium,
#   - the `tunerelay` systemd --user service (the daemon),
#   - the Omarchy shell plugin (symlinked, so `git pull` updates it),
#   - a default ~/.tunerelay/config.toml (never overwritten).
# The browser extension is loaded by hand once; see the message at the end.

set -euo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
HOST_NAME="com.tunerelay.host"

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }
for tool in yt-dlp codex rsync ssh; do
  command -v "$tool" >/dev/null || echo "warning: $tool is not on PATH" >&2
done

echo "Installing the tunerelay package…"
uv tool install --force --reinstall "$REPO"

# The extension ID follows from the pinned public key in its manifest.
key=$(sed -n 's/.*"key": *"\([^"]*\)".*/\1/p' "$REPO/extension/manifest.json")
extension_id=$(printf '%s' "$key" | base64 -d | sha256sum | head -c32 | tr '0-9a-f' 'a-p')

echo "Registering the native messaging host for extension $extension_id…"
for dir in \
  "$HOME/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts" \
  "$HOME/.config/google-chrome/NativeMessagingHosts" \
  "$HOME/.config/chromium/NativeMessagingHosts"; do
  mkdir -p "$dir"
  cat >"$dir/$HOST_NAME.json" <<JSON
{
  "name": "$HOST_NAME",
  "description": "TuneRelay capture host",
  "path": "$BIN/tunerelay-host",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://$extension_id/"]
}
JSON
done

echo "Installing the systemd user service…"
mkdir -p "$HOME/.config/systemd/user"
cat >"$HOME/.config/systemd/user/tunerelay.service" <<UNIT
[Unit]
Description=TuneRelay daemon (process and deliver captured songs)
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart=$BIN/tunerelay daemon
Restart=always
RestartSec=5
Environment=PATH=$BIN:${OMARCHY_PATH:-/usr/share/omarchy}/bin:/usr/local/bin:/usr/bin

[Install]
WantedBy=graphical-session.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now tunerelay.service
systemctl --user restart tunerelay.service

echo "Linking the Omarchy shell plugin…"
mkdir -p "$HOME/.config/omarchy/plugins"
ln -sfn "$REPO/shell-plugin/dagd.tunerelay" "$HOME/.config/omarchy/plugins/dagd.tunerelay"

"$BIN/tunerelay" status >/dev/null

cat <<DONE

TuneRelay is installed.

Remaining manual steps:
  1. Load the extension once in Brave / Chrome: open brave://extensions (or
     chrome://extensions), enable Developer mode, "Load unpacked" and pick
       $REPO/extension
     Its ID must be $extension_id.
  2. Add the TuneRelay widget to the Omarchy bar (it is the "dagd.tunerelay" plugin).
  3. Fill in the [delivery] and [scan] sections of ~/.tunerelay/config.toml
     (svc-02 hosts, SSH user, music folder, Navidrome URL/user and the pass entry).
  4. Accept svc-02's SSH host key once: ssh <user>@<host> true
DONE
