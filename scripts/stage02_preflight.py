#!/usr/bin/env python3
"""Read host prerequisite metadata; write only an ignored report under logs."""

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def tool_query(command):
    if shutil.which(command[0]) is None:
        return {"installed": False}
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
        return {
            "installed": True,
            "exit_code": result.returncode,
            "summary": "\n".join((result.stdout or result.stderr).splitlines()[:2])[:300],
        }
    except (OSError, subprocess.TimeoutExpired):
        return {"installed": True, "query_failed": True}


def main():
    root = Path(__file__).resolve().parents[1]
    available = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                available = round(int(line.split()[1]) / (1024 * 1024), 2)
    except (OSError, ValueError, IndexError):
        pass
    capabilities = set()
    cores = set()
    try:
        for block in Path("/proc/cpuinfo").read_text().split("\n\n"):
            fields = {}
            for line in block.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    fields[key.strip()] = value.strip()
            capabilities.update(fields.get("flags", "").split())
            if "physical id" in fields and "core id" in fields:
                cores.add((fields["physical id"], fields["core id"]))
    except OSError:
        pass
    controllers = []
    try:
        controllers = Path("/sys/fs/cgroup/cgroup.controllers").read_text().split()
    except OSError:
        pass
    report = {
        "stage": "02",
        "checkpoint": "tool_selection",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "architecture": platform.machine(),
        "host_python": platform.python_version(),
        "cpu_threads": os.cpu_count(),
        "physical_core_count_if_exposed": len(cores) or None,
        "cpu_features": {name: name in capabilities for name in ("sse4_2", "avx", "avx2", "fma")},
        "currently_available_ram_gib": available,
        "cgroup_v2": Path("/sys/fs/cgroup/cgroup.controllers").exists(),
        "cgroup_controllers_exposed": controllers,
        "tools": {
            "docker": tool_query(["docker", "--version"]),
            "compose": tool_query(["docker", "compose", "version", "--short"]),
            "github_cli": tool_query(["gh", "--version"]),
            "host_uv_required": False,
            "pnpm_required": False,
            "gpu_required": False,
        },
        "docker_daemon_reachable_without_sudo": False,
        "container_build_verified": False,
        "scientific_processing_executed": False,
        "note": "Missing Docker is expected until Stage 03. This command requests no sudo, installs nothing, starts no container, and collects no credentials.",
    }
    if shutil.which("docker"):
        try:
            status = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            report["docker_daemon_reachable_without_sudo"] = status.returncode == 0
            if status.returncode == 0:
                report["docker_server_version"] = status.stdout.strip()[:80]
        except (OSError, subprocess.TimeoutExpired):
            report["docker_daemon_query_failed"] = True
    directory = root / "logs" / "system"
    for candidate in (root / "logs", directory):
        if candidate.is_symlink():
            raise RuntimeError("A symbolic link blocks the diagnostic output directory.")
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    destination = directory / ("stage02_" + stamp + ".json")
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("STAGE_02_PREFLIGHT_BEGIN")
    print(json.dumps(report, indent=2))
    print("STAGE_02_PREFLIGHT_END")
    print("Saved diagnostic:", destination.relative_to(root))
    return 0


if __name__ == "__main__":
    sys.exit(main())

