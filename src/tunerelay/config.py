"""Where TuneRelay keeps its files, and the user-editable `config.toml`."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from tunerelay.jsondata import JsonObject

DEFAULT_CONFIG = """\
# TuneRelay configuration. Edit the [delivery] and [scan] sections for svc-02.

[tools]
ytdlp = "yt-dlp"
codex = "codex"
notify = "notify-send"
osd = "omarchy-osd"
player = "mpv"
ssh = "ssh"
rsync = "rsync"
password = "pass"

[codex]
timeout = 180
effort = "medium"

[delivery]
# "ssh" sends to the server with rsync over SSH, trying hosts in order (LAN first, then Tailscale).
transport = "ssh"
hosts = []          # e.g. ["svc-02.lan", "svc-02.tailnet.ts.net"]
user = ""           # SSH user on the server
music_dir = ""      # Navidrome music folder on the server
retry_interval = 3.0
max_attempts = 3

[scan]
# "subsonic" asks Navidrome to scan after each delivery; "none" relies on Navidrome's watcher.
method = "subsonic"
url = ""            # e.g. "http://svc-02.lan:4533"
user = ""
password_entry = "" # name of the `pass` entry holding the Navidrome password
"""


class ConfigError(Exception):
    """The config file is missing a value needed for the requested action."""


@dataclass(frozen=True)
class Tools:
    ytdlp: str
    codex: str
    notify: str
    osd: str
    player: str
    ssh: str
    rsync: str
    password: str


@dataclass(frozen=True)
class Delivery:
    transport: str
    hosts: list[str]
    user: str
    music_dir: str
    retry_interval: float
    max_attempts: int
    local_root: str
    local_fail_times: int


@dataclass(frozen=True)
class Scan:
    method: str
    url: str
    user: str
    password_entry: str


@dataclass(frozen=True)
class Config:
    home: Path
    tools: Tools
    codex_timeout: float
    codex_effort: str
    delivery: Delivery
    scan: Scan

    @property
    def inbox(self) -> Path:
        return self.home / "inbox"

    @property
    def covers(self) -> Path:
        return self.home / "covers"

    @property
    def database(self) -> Path:
        return self.home / "tunerelay.db"


def home_dir() -> Path:
    return Path(os.environ.get("TUNERELAY_HOME") or Path.home() / ".tunerelay")


def load() -> Config:
    """Read `config.toml` from the TuneRelay home, creating a commented default on first use."""
    home = home_dir()
    home.mkdir(parents=True, exist_ok=True)
    path = home / "config.toml"
    if not path.exists():
        path.write_text(DEFAULT_CONFIG)
    defaults = JsonObject(tomllib.loads(DEFAULT_CONFIG))
    data = JsonObject(tomllib.loads(path.read_text()))

    def section(name: str) -> JsonObject:
        return data.obj(name) or JsonObject({})

    def text(name: str, key: str) -> str:
        value = section(name).text(key)
        return value if value is not None else (defaults.obj(name) or JsonObject({})).text(key) or ""

    def number(name: str, key: str) -> float:
        value = section(name).number(key)
        if value is None:
            value = (defaults.obj(name) or JsonObject({})).number(key)
        return value or 0.0

    delivery = section("delivery")
    return Config(
        home=home,
        tools=Tools(
            ytdlp=text("tools", "ytdlp"),
            codex=text("tools", "codex"),
            notify=text("tools", "notify"),
            osd=text("tools", "osd"),
            player=text("tools", "player"),
            ssh=text("tools", "ssh"),
            rsync=text("tools", "rsync"),
            password=text("tools", "password"),
        ),
        codex_timeout=number("codex", "timeout"),
        codex_effort=text("codex", "effort"),
        delivery=Delivery(
            transport=text("delivery", "transport"),
            hosts=delivery.texts("hosts"),
            user=text("delivery", "user"),
            music_dir=text("delivery", "music_dir"),
            retry_interval=number("delivery", "retry_interval"),
            max_attempts=int(number("delivery", "max_attempts")),
            local_root=text("delivery", "local_root"),
            local_fail_times=int(delivery.number("local_fail_times") or 0),
        ),
        scan=Scan(
            method=text("scan", "method"),
            url=text("scan", "url"),
            user=text("scan", "user"),
            password_entry=text("scan", "password_entry"),
        ),
    )
