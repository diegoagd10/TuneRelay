"""Installing updated QML must refresh the running desktop, even when a rescan cannot."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("shell_running", [True, False])
@pytest.mark.parametrize("restart_fails", [True, False])
def test_install_refreshes_the_running_shell_or_prints_recovery(
    tmp_path: Path, shell_running: bool, restart_fails: bool
) -> None:
    home = tmp_path / "home"
    binaries = home / ".local" / "bin"
    binaries.mkdir(parents=True)
    log = tmp_path / "calls.log"
    scripts = {
        "uv": "exit 0",
        "tunerelay": "echo '{}'",
        "systemctl": "exit 0",
        "hyprctl": "echo '[]'",
        "omarchy-shell": 'exit "$TUNERELAY_FAKE_SHELL_STATUS"',
        "omarchy": (
            'test -L "$HOME/.config/omarchy/plugins/dagd.tunerelay" || exit 2\n'
            'echo "$*" >> "$TUNERELAY_INSTALL_LOG"\n'
            'exit "$TUNERELAY_FAKE_RESTART_STATUS"'
        ),
    }
    for name, body in scripts.items():
        executable = binaries / name
        executable.write_text("#!/bin/bash\n" + body + "\n")
        executable.chmod(0o755)
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": str(binaries) + os.pathsep + os.defpath,
        "TUNERELAY_INSTALL_LOG": str(log),
        "TUNERELAY_FAKE_SHELL_STATUS": "0" if shell_running else "1",
        "TUNERELAY_FAKE_RESTART_STATUS": "1" if restart_fails else "0",
    }
    result = subprocess.run(
        ["bash", str(Path(__file__).parents[1] / "install.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    if shell_running:
        assert log.exists(), "The installer left the running shell's old QML in memory"
        assert log.read_text().splitlines() == ["restart shell"]
        if restart_fails:
            assert "omarchy restart shell" in result.stderr
    else:
        assert not log.exists()
        assert "omarchy restart shell" in result.stdout
