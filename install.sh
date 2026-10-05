#!/bin/bash
# Install TuneRelay for the current user:
#   - the `tunerelay` and `tunerelay-host` executables (uv tool),
#   - the native messaging host manifest for Brave, Chrome and Chromium,
#   - the `tunerelay` systemd --user service (the daemon),
#   - the Omarchy shell plugin (symlinked to this checkout),
#   - a restart of the running Omarchy shell to load updated QML,
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

# A plugin rescan can reuse the old QML components from the running engine.
# Restart the shell after linking so updates actually reach the live window.
if command -v omarchy >/dev/null && command -v omarchy-shell >/dev/null && \
  omarchy-shell shell ping >/dev/null 2>&1; then
  echo "Restarting the Omarchy shell to load the updated TuneRelay window…"
  if ! omarchy restart shell; then
    echo "warning: the updated window is not loaded; run: omarchy restart shell" >&2
  fi
else
  echo "To load the updated window in a desktop session, run: omarchy restart shell"
fi

# Suggest a global key for the window. TuneRelay never edits the Hyprland config:
# two bindings on one key both run, so suggest the first candidate that is free.
TOGGLE="omarchy-shell shell toggle dagd.tunerelay"
suggest_key() {
  local binds
  binds=$(hyprctl binds -j 2>/dev/null) || return 1
  python3 - "$TOGGLE" "$binds" <<'PY'
import json, sys

toggle, binds = sys.argv[1], [b for b in json.loads(sys.argv[2]) if not b.get("submap")]
names = [(64, "SUPER"), (4, "CTRL"), (1, "SHIFT"), (8, "ALT")]

def combo(mask, key):
    return " + ".join([name for bit, name in names if mask & bit] + [key.upper()])

for b in binds:
    if b.get("description") == "TuneRelay":
        print(f"     Already bound to {combo(b['modmask'], b['key'])}.")
        sys.exit()
taken = {(b["modmask"], b["key"].upper()): b.get("description") or b["dispatcher"] for b in binds}
for mask in (64 | 4, 64 | 4 | 1, 64 | 4 | 8):
    if (mask, "M") in taken:
        print(f"     {combo(mask, 'M')} is taken ({taken[(mask, 'M')]}).")
        continue
    print("     Add to ~/.config/hypr/bindings.lua:")
    print(f'       o.bind("{combo(mask, "M")}", "TuneRelay", "{toggle}")')
    sys.exit()
print(f'     All suggested keys are taken: bind "{toggle}" to a key of your choice.')
PY
}
if ! key_hint=$(suggest_key); then
  key_hint="     Could not ask Hyprland which keys are free; check \`omarchy menu keybindings --print\`, then
     add to ~/.config/hypr/bindings.lua:
       o.bind(\"SUPER + CTRL + M\", \"TuneRelay\", \"$TOGGLE\")"
fi

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
  5. Optional: a global key to open the TuneRelay window (the bar icon works too).
$key_hint
DONE
