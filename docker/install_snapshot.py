"""Install fixed-snapshot packages inside a disposable image build only."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess

SNAPSHOT = "20261014T000000Z"
PRIMARY = "https://snapshot.debian.org/"
ALTERNATE = "https://snapshot-cloudflare.debian.org/"
SOURCE_SHA256 = "571346cacec76fb774207c4f63ecef7d50402d08f9cc2e1d7e09ffa358530db8"
PACKAGES = {"runtime": ["libgomp1"], "compiler": ["ca-certificates", "git", "cmake", "build-essential"]}
OPTIONS = ["-o", "Acquire::Retries=2", "-o", "Acquire::http::Timeout=30",
           "-o", "Acquire::https::Timeout=30", "-o", "Acquire::http::Pipeline-Depth=0",
           "-o", "Acquire::https::Pipeline-Depth=0", "-o", "Acquire::Queue-Mode=host",
           "-o", "Acquire::Languages=none"]


def run_command(arguments, timeout):
    process = subprocess.Popen(arguments, start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print("SNAPSHOT_COMMAND_TIMEOUT: terminating the package-download process group", flush=True)
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        return 124


def checked_template(data):
    # Only a hostname substitution is allowed; dates, suites, keys and options stay fixed.
    canonical = data.replace(ALTERNATE.encode(), PRIMARY.encode())
    if hashlib.sha256(canonical).hexdigest() != SOURCE_SHA256:
        raise ValueError("Unexpected Debian source file; no package operation was started.")
    if PRIMARY.encode() in data and ALTERNATE.encode() in data:
        raise ValueError("Mixed snapshot endpoints are unsupported.")
    return canonical, ALTERNATE if ALTERNATE.encode() in data else PRIMARY


def install(role, sources, receipt, execute=run_command):
    if role not in PACKAGES:
        raise ValueError("Unknown package role.")
    canonical, active = checked_template(sources.read_bytes())
    endpoints = [active, ALTERNATE if active == PRIMARY else PRIMARY]
    attempts = []
    for endpoint in endpoints:
        sources.write_bytes(canonical.replace(PRIMARY.encode(), endpoint.encode()))
        print("SNAPSHOT_FETCH: " + role + " " + endpoint + " at " + SNAPSHOT, flush=True)
        updated = execute(["apt-get", *OPTIONS, "--error-on=any", "update"], timeout=300)
        installed = None
        if updated == 0:
            installed = execute(["apt-get", *OPTIONS, "install", "-y", "--no-install-recommends", *PACKAGES[role]], timeout=1200)
        attempts.append({"endpoint": endpoint, "update_exit": updated, "install_exit": installed})
        if updated == 0 and installed == 0:
            record = {"schema_version": 1, "status": "passed", "role": role, "snapshot": SNAPSHOT,
                      "endpoint": endpoint, "attempts": attempts, "requested_packages": PACKAGES[role],
                      "source_sha256": hashlib.sha256(sources.read_bytes()).hexdigest(),
                      "apt_authentication": "Debian archive signatures and package hashes required"}
            receipt.write_text(json.dumps(record, indent=2) + "\n")
            print("SNAPSHOT_FETCH_PASSED: " + json.dumps(record, sort_keys=True), flush=True)
            return record
    print("SNAPSHOT_FETCH_FAILED: " + json.dumps({"role": role, "snapshot": SNAPSHOT, "attempts": attempts}), flush=True)
    raise RuntimeError("Both pinned Debian snapshot endpoints failed; inspect the build log and retry. No rolling mirror was used.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=PACKAGES, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("ROCKET_CONTAINER_BUILD") != "1":
        raise SystemExit("This installer runs only through the project's disposable Docker image build.")
    install(args.role, Path("/etc/apt/sources.list.d/debian.sources"), args.receipt)


if __name__ == "__main__":
    main()
