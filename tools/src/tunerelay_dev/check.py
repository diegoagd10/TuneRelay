"""`uv run check`: the quality gate. Every step must pass."""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def audit_command() -> list[str]:
    """Vulnerability audit of the locked dependencies (needs network access to the advisory database)."""
    requirements = Path(tempfile.mkdtemp(prefix="tunerelay-audit-")) / "requirements.txt"
    subprocess.run(
        [
            "uv",
            "export",
            "--quiet",
            "--frozen",
            "--all-groups",
            "--no-emit-workspace",
            "-o",
            str(requirements),
        ],
        cwd=ROOT,
        check=True,
    )
    return ["pip-audit", "--strict", "--disable-pip", "--progress-spinner", "off", "-r", str(requirements)]


STEPS: list[tuple[str, list[str] | None]] = [
    ("lock is current (every dependency resolves on PyPI)", ["uv", "lock", "--check"]),
    ("ruff lint", ["ruff", "check", "."]),
    ("ruff format", ["ruff", "format", "--check", "."]),
    ("pyright (strict on src/)", ["pyright"]),
    ("deptry (imports match declared dependencies)", ["deptry", "src"]),
    ("pip-audit (known vulnerabilities)", None),
    (
        "tests and coverage >= 95%",
        ["pytest", "-n", "auto", "--cov=tunerelay", "--cov-report=term-missing", "--cov-fail-under=95"],
    ),
]


def main() -> None:
    failed: list[str] = []
    for name, command in STEPS:
        print(f"\n== {name}", flush=True)
        if subprocess.run(command or audit_command(), cwd=ROOT, check=False).returncode != 0:
            failed.append(name)
    print()
    if failed:
        print("FAILED: " + "; ".join(failed))
        sys.exit(1)
    print("All checks passed.")
