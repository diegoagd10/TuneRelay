"""Optional Navidrome library scan via the Subsonic `startScan` endpoint."""

import hashlib
import secrets
import subprocess
import urllib.parse
import urllib.request

from tunerelay.config import Config, ConfigError, require_filled
from tunerelay.jsondata import JsonObject

API_VERSION = "1.16.1"
CLIENT = "TuneRelay"


class ScanError(Exception):
    """Navidrome could not be asked to scan."""


def password(cfg: Config) -> str:
    """Read the Navidrome password from the configured `pass` entry."""
    try:
        result = subprocess.run(
            [cfg.tools.password, "show", cfg.scan.password_entry],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ScanError(f"could not read the password: {error}") from error
    if result.returncode != 0 or not result.stdout.strip():
        raise ScanError(f"could not read the password from pass entry {cfg.scan.password_entry}")
    return result.stdout.splitlines()[0]


def trigger_scan(cfg: Config) -> None:
    """Ask Navidrome to scan now. Does nothing when `scan.method = "none"`."""
    scan = cfg.scan
    if scan.method == "none":
        return
    if scan.method != "subsonic":
        raise ConfigError(f'scan.method must be "subsonic" or "none", not "{scan.method}"')
    require_filled(
        "scan", {"url": bool(scan.url), "user": bool(scan.user), "password_entry": bool(scan.password_entry)}
    )
    if not scan.url.startswith(("http://", "https://")):
        raise ConfigError("scan.url must start with http:// or https://")
    salt = secrets.token_hex(8)
    token = hashlib.md5((password(cfg) + salt).encode()).hexdigest()  # noqa: S324 - required by the Subsonic API
    query = urllib.parse.urlencode(
        {"u": scan.user, "t": token, "s": salt, "v": API_VERSION, "c": CLIENT, "f": "json"}
    )
    url = f"{scan.url.rstrip('/')}/rest/startScan.view?{query}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - scheme checked above
            body = response.read().decode(errors="replace")
    except OSError as error:
        raise ScanError(f"Navidrome did not answer: {error}") from error
    try:
        answer = (JsonObject.parse(body).obj("subsonic-response") or JsonObject({})).text("status")
    except ValueError:
        answer = None
    if answer != "ok":
        raise ScanError(f"Navidrome refused the scan: {body[:200]}")
