"""Run the API test suite, but only if no other pytest is running on this machine.

    py -3.11 scripts/run_api_tests.py                      # the whole suite
    py -3.11 scripts/run_api_tests.py tests/test_worker.py -q

Why: every pytest session drops and recreates the shared test database (`cdl_test` on `api-db-1`). A second session
running at the same time kills the first one's connections, and both report failures that are not real bugs. Two
Claude sessions, or Claude plus Codex, hit this on 2026-10-21. This script is the check: it refuses to start while
another pytest is alive, and tells you which process to wait for.

It needs Docker Desktop and the `api-db-1` container to be running (it does not start them).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1] / "api"
PYTHON = API_DIR / ".venv" / "Scripts" / "python.exe"
# Only real interpreters count (python, py, pytest executables). A shell whose command text merely mentions pytest,
# or the query below, must not match.
FIND_PYTEST = (
    "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and "
    "$_.Name -match '^(python|pythonw|py|pytest)[0-9.]*\.exe$' -and "
    "$_.CommandLine -match '(-m\\s+pytest|pytest(\\.exe)?\\s|py\\.test)' } | "
    "ForEach-Object { [pscustomobject]@{ pid = $_.ProcessId; command = $_.CommandLine.Substring(0, "
    "[Math]::Min(110, $_.CommandLine.Length)) } } | ConvertTo-Json -Compress"
)


def other_pytest_processes() -> list[dict]:
    """The pytest processes running right now, other than this one, as [{"pid": ..., "command": ...}]."""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", FIND_PYTEST], capture_output=True, text=True)
    text = result.stdout.strip()
    if result.returncode != 0:
        raise RuntimeError(f"could not list processes: {result.stderr.strip()[:200]}")
    if not text:
        return []
    found = json.loads(text)
    return [item for item in (found if isinstance(found, list) else [found]) if item["pid"] != os.getpid()]


def main(argv: list[str]) -> int:
    running = other_pytest_processes()
    if running:
        print("Another pytest is already running. Do not start a second one: it would drop the shared test database")
        print("under the first and both runs would show failures that are not real. Wait for it to finish, then retry.")
        for item in running:
            print(f"  pid {item['pid']}: {item['command']}")
        return 2
    return subprocess.call([str(PYTHON), "-m", "pytest", "-p", "no:cacheprovider", *argv], cwd=API_DIR)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
