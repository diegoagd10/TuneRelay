"""Sending a tagged song to the Navidrome music folder on svc-02, and verifying the copy.

The file is copied to a hidden temporary name, verified by size and SHA-256, and
only then moved into place, so an interrupted transfer never looks like a
conflict and a bad copy never reaches the library.
"""

import hashlib
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Protocol

from tunerelay.config import Config, ConfigError, require_filled
from tunerelay.store import Proposal

UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
MAX_COMPONENT = 120
COVER_NAME = "cover.jpg"
SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]


class DeliveryError(Exception):
    """A transfer attempt failed; it may succeed when retried."""


class DeliveryOutcome(StrEnum):
    DELIVERED = "delivered"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class DeliveryResult:
    outcome: DeliveryOutcome
    remote_path: PurePosixPath


class Transport(Protocol):
    """Paths are relative to the music folder."""

    def exists(self, path: PurePosixPath) -> bool: ...
    def put(self, local: Path, path: PurePosixPath) -> None: ...
    def size(self, path: PurePosixPath) -> int: ...
    def checksum(self, path: PurePosixPath) -> str: ...
    def publish(self, source: PurePosixPath, dest: PurePosixPath, *, overwrite: bool) -> bool:
        """Atomically rename `source` to `dest`. Without `overwrite`, returns False (and leaves
        `source` in place) if `dest` exists, even if it appeared a moment ago."""
        ...

    def remove(self, path: PurePosixPath) -> None: ...


def sanitize(component: str) -> str:
    cleaned = UNSAFE.sub("_", component).strip().strip(".").strip()
    return cleaned[:MAX_COMPONENT].rstrip(" .") or "_"


def destination_path(proposal: Proposal) -> PurePosixPath:
    """`<Album artist>/<Album> (<Year>)/<NN> - <Title>.m4a`, with unsafe characters replaced."""
    album = f"{proposal.album} ({proposal.year})" if proposal.year is not None else proposal.album
    name = f"{proposal.track:02d} - {proposal.title}"
    return PurePosixPath(
        sanitize(proposal.album_artist or proposal.artist), sanitize(album), sanitize(name) + ".m4a"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _send_verified(transport: Transport, local: Path, dest: PurePosixPath, *, overwrite: bool) -> bool:
    """Copy, verify, then publish. Returns False if `dest` appeared and `overwrite` is not allowed."""
    temporary = dest.with_name(f".{dest.name}.tunerelay-part")
    transport.put(local, temporary)
    expected_size, expected_sum = local.stat().st_size, sha256(local)
    remote_size, remote_sum = transport.size(temporary), transport.checksum(temporary)
    if (remote_size, remote_sum) != (expected_size, expected_sum):
        transport.remove(temporary)
        raise DeliveryError(
            f"verification failed for {dest}: sent {expected_size} bytes, server has {remote_size} bytes"
        )
    if transport.publish(temporary, dest, overwrite=overwrite):
        return True
    transport.remove(temporary)
    return False


def _same_file(transport: Transport, local: Path, remote: PurePosixPath) -> bool:
    return (transport.size(remote), transport.checksum(remote)) == (local.stat().st_size, sha256(local))


def deliver(
    audio: Path, proposal: Proposal, transport: Transport, *, replace: PurePosixPath | None
) -> DeliveryResult:
    """Send the audio and its folder cover. An existing file is only overwritten when it is `replace`
    (the path the user chose to replace); a byte-identical one means an earlier attempt already got there."""
    dest = destination_path(proposal)
    overwrite = dest == replace
    already_there = transport.exists(dest) and not overwrite
    if not already_there and not _send_verified(transport, audio, dest, overwrite=overwrite):
        already_there = True  # another file appeared at the destination during the copy
    if already_there and not _same_file(transport, audio, dest):
        return DeliveryResult(DeliveryOutcome.CONFLICT, dest)
    cover_dest = dest.parent / COVER_NAME
    if proposal.cover and Path(proposal.cover).exists() and (overwrite or not transport.exists(cover_dest)):
        # A folder cover that appears meanwhile belongs to someone else; keeping it is fine.
        _send_verified(transport, Path(proposal.cover), cover_dest, overwrite=overwrite)
    return DeliveryResult(DeliveryOutcome.DELIVERED, dest)


class LocalTransport:
    """A local directory standing in for the Navidrome library. Can fail its first N transfers."""

    def __init__(self, root: Path, fail_times: int) -> None:
        self._root = root
        self._failures_left = fail_times

    def _path(self, path: PurePosixPath) -> Path:
        return self._root / path

    def exists(self, path: PurePosixPath) -> bool:
        return self._path(path).exists()

    def put(self, local: Path, path: PurePosixPath) -> None:
        if self._failures_left > 0:
            self._failures_left -= 1
            raise DeliveryError("simulated transfer failure")
        if not self._root.is_dir():
            raise DeliveryError(f"library folder {self._root} does not exist")
        self._path(path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, self._path(path))

    def size(self, path: PurePosixPath) -> int:
        return self._path(path).stat().st_size

    def checksum(self, path: PurePosixPath) -> str:
        return sha256(self._path(path))

    def publish(self, source: PurePosixPath, dest: PurePosixPath, *, overwrite: bool) -> bool:
        if overwrite:
            self._path(source).replace(self._path(dest))
            return True
        try:
            # link(2) refuses an existing target atomically, unlike rename(2).
            os.link(self._path(source), self._path(dest))
        except FileExistsError:
            return False
        self._path(source).unlink()
        return True

    def remove(self, path: PurePosixPath) -> None:
        self._path(path).unlink(missing_ok=True)


class SshTransport:
    """rsync over SSH to the first reachable host (LAN first, then Tailscale)."""

    def __init__(self, ssh: str, rsync: str, hosts: list[str], user: str, music_dir: str) -> None:
        self._ssh = ssh
        self._rsync = rsync
        self._hosts = hosts
        self._user = user
        self._root = PurePosixPath(music_dir)
        self._target: str | None = None

    def _login(self, host: str) -> str:
        return f"{self._user}@{host}" if self._user else host

    def _connect(self) -> str:
        if self._target is None:
            for host in self._hosts:
                login = self._login(host)
                probe = subprocess.run(
                    [self._ssh, *SSH_OPTIONS, login, "true"], capture_output=True, timeout=30, check=False
                )
                if probe.returncode == 0:
                    self._target = login
                    break
            else:
                raise DeliveryError(f"svc-02 is unreachable (tried {', '.join(self._hosts)})")
        return self._target

    def _remote(self, *words: str) -> subprocess.CompletedProcess[str]:
        command = " ".join(shlex.quote(word) for word in words)
        try:
            result = subprocess.run(
                [self._ssh, *SSH_OPTIONS, self._connect(), command],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise DeliveryError(f"ssh timed out: {words[0]}") from error
        if result.returncode == 255:
            self._target = None
            raise DeliveryError(f"ssh failed: {result.stderr.strip()}")
        return result

    def _checked(self, *words: str) -> str:
        result = self._remote(*words)
        if result.returncode != 0:
            raise DeliveryError(f"{words[0]} failed on the server: {result.stderr.strip()}")
        return result.stdout

    def _full(self, path: PurePosixPath) -> str:
        return str(self._root / path)

    def exists(self, path: PurePosixPath) -> bool:
        return self._remote("test", "-e", self._full(path)).returncode == 0

    def put(self, local: Path, path: PurePosixPath) -> None:
        target = self._connect()
        self._checked("mkdir", "-p", "--", self._full(path.parent))
        shell = " ".join([self._ssh, *SSH_OPTIONS])
        try:
            result = subprocess.run(
                [
                    self._rsync,
                    "--protect-args",
                    "--times",
                    "-e",
                    shell,
                    str(local),
                    f"{target}:{self._full(path)}",
                ],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise DeliveryError("rsync timed out") from error
        if result.returncode != 0:
            raise DeliveryError(f"rsync failed: {result.stderr.strip() or result.returncode}")

    def size(self, path: PurePosixPath) -> int:
        return int(self._checked("stat", "-c", "%s", "--", self._full(path)).strip())

    def checksum(self, path: PurePosixPath) -> str:
        return self._checked("sha256sum", "--", self._full(path)).split()[0]

    def publish(self, source: PurePosixPath, dest: PurePosixPath, *, overwrite: bool) -> bool:
        if overwrite:
            self._checked("mv", "-f", "--", self._full(source), self._full(dest))
            return True
        # `ln` (link(2)) refuses an existing target atomically, unlike `mv`.
        if self._remote("ln", "-T", "--", self._full(source), self._full(dest)).returncode != 0:
            if self.exists(dest):
                return False
            raise DeliveryError(f"could not publish {dest} on the server")
        self._checked("rm", "-f", "--", self._full(source))
        return True

    def remove(self, path: PurePosixPath) -> None:
        self._checked("rm", "-f", "--", self._full(path))


def transport_for(cfg: Config) -> Transport:
    settings = cfg.delivery
    if settings.transport == "local":
        return LocalTransport(Path(settings.local_root), settings.local_fail_times)
    if settings.transport != "ssh":
        raise ConfigError(f'delivery.transport must be "ssh" or "local", not "{settings.transport}"')
    require_filled("delivery", {"hosts": bool(settings.hosts), "music_dir": bool(settings.music_dir)})
    return SshTransport(cfg.tools.ssh, cfg.tools.rsync, settings.hosts, settings.user, settings.music_dir)
