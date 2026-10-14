#!/usr/bin/env python3
"""Read-only prerequisite inspection; only the report file under logs is written."""

import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def command_status(command):
    if shutil.which(command[0]) is None:
        return {"installed": False}
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=5, check=False
        )
        lines = (completed.stdout or completed.stderr).strip().splitlines()
        return {
            "installed": True,
            "exit_code": completed.returncode,
            "summary": "\n".join(lines[:3])[:500],
        }
    except subprocess.TimeoutExpired:
        return {"installed": True, "timed_out": True}
    except OSError:
        return {"installed": True, "query_failed": True}


def git_identity_ready(repo):
    present = []
    for field in ("user.name", "user.email"):
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), "config", "--get", field],
                capture_output=True, text=True, timeout=5, check=False,
            )
            present.append(result.returncode == 0 and bool(result.stdout.strip()))
        except (OSError, subprocess.TimeoutExpired):
            present.append(False)
    return all(present)


def main():
    root = Path(__file__).resolve().parents[1]
    os_info = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key in {"NAME", "PRETTY_NAME", "ID", "ID_LIKE", "VERSION_ID"}:
                parsed = shlex.split(value)
                os_info[key] = parsed[0] if parsed else ""
    except OSError:
        os_info = {"read_failed": True}

    ram_gib = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                ram_gib = round(int(line.split()[1]) / (1024 * 1024), 2)
                break
    except (OSError, ValueError, IndexError):
        pass

    disk = shutil.disk_usage(root)
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%S_%fZ")
    report = {
        "stage": "01",
        "timestamp_utc": now.isoformat(),
        "os": os_info,
        "architecture": platform.machine(),
        "cpu_threads": os.cpu_count(),
        "ram_gib": ram_gib,
        "free_disk_gib": round(disk.free / (1024 ** 3), 2),
        "python": platform.python_version(),
        "git_identity_configured": git_identity_ready(root),
        "tools": {},
        "inspection_policy": "No installs, network requests, or container starts; no credentials collected.",
    }
    queries = {
        "git": ["git", "--version"],
        "docker": ["docker", "--version"],
        "docker_compose": ["docker", "compose", "version", "--short"],
        "uv": ["uv", "--version"],
        "github_cli": ["gh", "--version"],
        "nvidia_optional": [
            "nvidia-smi", "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ],
    }
    for name, command in queries.items():
        report["tools"][name] = command_status(command)
    report["tools"]["pnpm_optional"] = {
        "installed": shutil.which("pnpm") is not None,
        "version_not_queried": "Avoid a possible Corepack download; no JavaScript UI is required yet.",
    }

    report["docker_daemon_reachable"] = False
    if shutil.which("docker"):
        try:
            result = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            report["docker_daemon_reachable"] = result.returncode == 0
            if result.returncode == 0:
                report["docker_server_version"] = result.stdout.strip()[:80]
        except (OSError, subprocess.TimeoutExpired):
            report["docker_daemon_query_failed"] = True

    destination = root / "logs" / "system" / ("stage01_" + run_id + ".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("SYSTEM_REPORT_BEGIN")
    print(json.dumps(report, indent=2))
    print("SYSTEM_REPORT_END")
    print("Saved diagnostic:", destination.relative_to(root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
