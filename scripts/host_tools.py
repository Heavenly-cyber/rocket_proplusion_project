"""Official signed APT packages, explicit sudo, no removals or global upgrades."""

import os
import platform
import re
import shutil
from pathlib import Path

from host_common import MESSAGES, ProjectError, commit_files, folder, safe, sha, save_checkpoint

DOCKER_VERSION = "29.9.0"
COMPOSE_VERSION = "5.6.0"
GH_VERSION = "2.102.0"
GH_KEY_SHA = "6084d5d7bd8e288441e0e94fc6275570895da18e6751f70f057485dc2d1a811b"
DOCKER_FINGERPRINT = "9DC858229FC7DD38854AE2D88D81803C0EBFCD88"
PACKAGES = ["docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin", "docker-compose-plugin", "gh"]


def installed(runner, package):
    code, output = runner.run(["dpkg-query", "-W", "-f=${db:Status-Status} ${Version}", package], check=False, logged=False)
    if code == 0 and output.startswith("installed "):
        return output.split()[1]
    return None


def version_number(version):
    return version.split(":")[-1].split("-")[0]


def apt_version(runner, package, wanted=None):
    _, output = runner.run(["apt-cache", "madison", package], logged=False)
    versions = [line.split("|")[1].strip() for line in output.splitlines() if "|" in line]
    selected = [value for value in versions if wanted is None or version_number(value) == wanted]
    if not selected:
        raise ProjectError("Selected signed APT package is unavailable: " + package + " " + str(wanted))
    return selected[0]


def system_file(runner, path, data):
    destination = Path(path)
    if destination.is_symlink():
        raise ProjectError("Existing system configuration symlink preserved: " + path)
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != data:
            raise ProjectError("Existing system configuration preserved: " + path)
        return
    folder("tmp/host-tools")
    temporary = safe("tmp/host-tools/" + destination.name + "-" + sha(data)[:16])
    if temporary.exists() and temporary.read_bytes() != data:
        raise ProjectError("Existing tool-setup temporary differs.")
    if not temporary.exists():
        temporary.write_bytes(data)
    runner.run(["sudo", "install", "-m", "0644", str(temporary), path])


def add_repositories(runner):
    runner.run(["sudo", "install", "-d", "-m", "0755", "/etc/apt/keyrings"])
    folder("tmp/host-tools")
    docker_key = safe("tmp/host-tools/docker.asc")
    gh_key = safe("tmp/host-tools/github.gpg")
    for url, path in [
        ("https://download.docker.com/linux/ubuntu/gpg", docker_key),
        ("https://cli.github.com/packages/githubcli-archive-keyring.gpg", gh_key),
    ]:
        runner.run(["curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
                    "--max-time", "90", "--output", str(path), url])
    _, fingerprints = runner.run(["gpg", "--homedir", str(folder("tmp/host-tools/gnupg")),
                                   "--batch", "--with-colons", "--show-keys", str(docker_key)], logged=False)
    if DOCKER_FINGERPRINT not in fingerprints:
        raise ProjectError("Docker signing-key fingerprint differs; no repository added.")
    if sha(gh_key.read_bytes()) != GH_KEY_SHA:
        raise ProjectError("GitHub CLI signing key differs from the reviewed official checksum.")
    system_file(runner, "/etc/apt/keyrings/rocket-nozzle-docker.asc", docker_key.read_bytes())
    system_file(runner, "/etc/apt/keyrings/rocket-nozzle-github.gpg", gh_key.read_bytes())
    system_file(runner, "/etc/apt/sources.list.d/rocket-nozzle-docker.sources", b"Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: noble\nComponents: stable\nArchitectures: amd64\nSigned-By: /etc/apt/keyrings/rocket-nozzle-docker.asc\n")
    system_file(runner, "/etc/apt/sources.list.d/rocket-nozzle-github.sources", b"Types: deb\nURIs: https://cli.github.com/packages\nSuites: stable\nComponents: main\nArchitectures: amd64\nSigned-By: /etc/apt/keyrings/rocket-nozzle-github.gpg\n")


def ensure_tools(runner, install=True):
    if os.getuid() == 0:
        raise ProjectError("Run the launcher as your normal user; it requests sudo only for system commands.")
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ProjectError("This initial installer is for Linux x86_64. Other CPUs need a reviewed profile.")
    versions = {name: installed(runner, name) if shutil.which("dpkg-query") else None for name in PACKAGES}
    saved_path = safe("configs/host-tools.lock.json")
    saved = None
    if saved_path.is_file():
        import json
        saved = json.loads(saved_path.read_text())
    released = runner.run(["git", "rev-parse", "--verify", "--quiet", "refs/tags/v0.3.0"], check=False, logged=False)[0] == 0
    portable_existing = released and all(shutil.which(name) for name in ("sudo", "docker", "gh"))
    wanted = {"docker-ce": DOCKER_VERSION, "docker-ce-cli": DOCKER_VERSION,
              "docker-compose-plugin": COMPOSE_VERSION, "gh": GH_VERSION}
    for package, version in wanted.items():
        if versions[package] and version_number(versions[package]) != version:
            raise ProjectError("Existing " + package + " differs; no upgrade/downgrade was applied.")
    if not all(versions.values()) and not portable_existing:
        if not install:
            raise ProjectError("Docker/Compose/GitHub CLI are not installed. Run setup first.")
        release = {}
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                release[key] = value.strip('"')
        if release.get("ID") not in {"pop", "ubuntu"} or release.get("VERSION_ID") != "24.04":
            raise ProjectError("Automated APT setup is limited to Pop!_OS/Ubuntu 24.04; existing Docker is portable.")
        conflicts = [name for name in ["docker.io", "docker-compose", "docker-compose-v2", "docker-doc",
                     "docker-buildx", "podman-docker", "containerd", "runc"] if installed(runner, name)]
        if conflicts:
            raise ProjectError("Conflicting packages preserved: " + ", ".join(conflicts))
        # Refuse duplicate external repo entries; never rewrite someone else's Signed-By choice.
        for entry in Path("/etc/apt/sources.list.d").glob("*"):
            if entry.is_file() and not entry.name.startswith("rocket-nozzle-"):
                text = entry.read_text(errors="replace")
                if "download.docker.com/linux/ubuntu" in text or "cli.github.com/packages" in text:
                    raise ProjectError("Existing external APT source preserved: " + str(entry))
        print("Installing official signed prerequisites. sudo uses your local terminal.", flush=True)
        runner.run(["sudo", "-v"], interactive=True)
        runner.run(["sudo", "apt-get", "update"], timeout=600)
        runner.run(["sudo", "apt-get", "install", "-y", "--no-remove", "--no-install-recommends",
                    "ca-certificates", "curl", "gnupg"], timeout=900)
        add_repositories(runner)
        runner.run(["sudo", "apt-get", "update"], timeout=600)
        selected = {name: versions[name] or (saved["apt_packages"][name] if saved else apt_version(runner, name, wanted.get(name))) for name in PACKAGES}
        runner.run(["sudo", "apt-get", "install", "-y", "--no-remove", "--no-install-recommends",
                    *[name + "=" + value for name, value in selected.items()]], timeout=1800)
        versions = {name: installed(runner, name) for name in PACKAGES}
        if versions != selected:
            raise ProjectError("Installed APT versions differ from the selected package set.")
    if not shutil.which("sudo") or not shutil.which("docker") or not shutil.which("gh"):
        raise ProjectError("Selected host executables are not reachable on PATH.")
    runner.run(["sudo", "-v"], interactive=True)
    docker = ["sudo", "docker", "--host", "unix:///var/run/docker.sock"]
    code, _ = runner.run(docker + ["info"], check=False, logged=False)
    if code:
        runner.run(["sudo", "systemctl", "start", "docker"], timeout=90)
    _, engine = runner.run(docker + ["version", "--format", "{{.Server.Version}}"], logged=False)
    _, compose = runner.run(docker + ["compose", "version", "--short"], logged=False)
    _, gh = runner.run(["gh", "--version"], logged=False)
    if engine.strip() != DOCKER_VERSION or compose.strip().lstrip("v") != COMPOSE_VERSION:
        raise ProjectError("Docker Engine/Compose running versions differ from the selected versions.")
    if not re.match(r"gh version " + re.escape(GH_VERSION) + r"\b", gh):
        raise ProjectError("The active GitHub CLI differs from its package pin.")
    _, info = runner.run(docker + ["info", "--format", "{{json .}}"], logged=False)
    import json
    record = json.loads(info)
    if record.get("CgroupVersion") != "2" or "rootless" in str(record.get("SecurityOptions", [])):
        raise ProjectError("Expected rootful Docker with cgroup v2; existing daemon configuration preserved.")
    receipt = {"schema_version": 1, "engine": engine.strip(), "compose": compose.strip(),
               "github_cli": GH_VERSION, "apt_packages": versions, "cgroup_version": "2",
               "access": "explicit_sudo_local_unix_socket", "job_user": "host_uid_gid"}
    path = safe("configs/host-tools.lock.json")
    if path.exists():
        if json.loads(path.read_text()) != receipt:
            if released:
                from host_common import write_json
                write_json("logs/setup/current-host-tools.json", receipt)
            else:
                raise ProjectError("Host tools differ from the saved receipt. Return the diagnostic before changing pins.")
    else:
        save_checkpoint(runner, {"configs/host-tools.lock.json": receipt}, MESSAGES["host"])
    commit_files(runner, ["configs/host-tools.lock.json"], MESSAGES["host"])
    return docker
