"""Bounded disposable jobs; only resources owned by this repository are removed."""

import json
import os
import uuid
from contextlib import contextmanager

from host_common import ROOT, ProjectError, folder, sha, stamp, write_json

OWNER = sha(str(ROOT).encode())[:24]
OWNER_KEY = "org.heavenly.rocket.owner"
RUN_KEY = "org.heavenly.rocket.run"


def run_id(kind):
    return kind + "-" + stamp().lower() + "-" + uuid.uuid4().hex[:8]


def mount(source, destination, read_only=False):
    if "," in str(source) or "\n" in str(source):
        raise ProjectError("Docker bind paths containing commas/newlines are unsupported.")
    return ["--mount", "type=bind,src=" + str(source) + ",dst=" + destination + (",readonly" if read_only else "")]


class Jobs:
    def __init__(self, runner, docker):
        self.runner = runner
        self.docker = docker

    def call(self, *args, **kwargs):
        return self.runner.run(self.docker + list(args), **kwargs)

    def inspect(self, resource):
        code, data = self.call("inspect", resource, check=False, logged=False)
        if code:
            if "No such object" in data or "No such container" in data or "No such image" in data:
                return None
            raise ProjectError("Docker inspection failed; absence cannot be verified.")
        return json.loads(data)[0]

    def assert_contract(self, item, memory, cpus, network=None):
        host = item["HostConfig"]
        if item["Config"].get("Labels", {}).get(OWNER_KEY) != OWNER:
            raise ProjectError("Container ownership label mismatch.")
        if item["Config"]["User"] != "%d:%d" % (os.getuid(), os.getgid()):
            raise ProjectError("Container user differs from host UID/GID.")
        if not host["ReadonlyRootfs"] or host.get("Privileged"):
            raise ProjectError("Container filesystem/privilege contract failed.")
        if "ALL" not in [value.upper() for value in (host.get("CapDrop") or [])]:
            raise ProjectError("Container did not drop all capabilities.")
        if not any("no-new-privileges" in opt for opt in host.get("SecurityOpt", [])):
            raise ProjectError("Container no-new-privileges check failed.")
        if host["Memory"] != memory or host["MemorySwap"] != memory or host["NanoCpus"] != int(cpus * 1e9):
            raise ProjectError("Container CPU/memory limits differ from the profile.")
        if not 0 < host["PidsLimit"] <= 256 or host["RestartPolicy"]["Name"] not in {"no", ""}:
            raise ProjectError("Container PID/restart contract failed.")
        if host.get("PortBindings"):
            raise ProjectError("Container published a host port.")
        if network and host["NetworkMode"] != network:
            raise ProjectError("Container network differs from the requested mode.")
        for binding in item["Mounts"]:
            if binding["Destination"] == "/var/run/docker.sock":
                raise ProjectError("Docker socket must not be mounted in a job.")

    def job(self, image, args, *, kind="job", network="none", extra_mounts=(),
            entrypoint=None, timeout=1200, expected_exit=0, env=None):
        name = run_id(kind)
        output = folder("resutls/" + name)
        log = folder("logs/" + name)
        resources = "logs/" + name + "/resources.json"
        write_json(resources, {"owner": OWNER, "name": name, "container": name, "status": "creating"})
        options = ["create", "--name", name, "--label", OWNER_KEY + "=" + OWNER,
                   "--label", RUN_KEY + "=" + name, "--user", "%d:%d" % (os.getuid(), os.getgid()),
                   "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                   "--cpus", "2", "--memory", "2g", "--memory-swap", "2g", "--pids-limit", "256",
                   "--network", network, "--restart", "no", "--init",
                   "--tmpfs", "/tmp:rw,nosuid,nodev,size=1073741824,mode=1777"]
        options += mount(output, "/out")
        for source, destination, readonly in extra_mounts:
            options += mount(source, destination, readonly)
        if entrypoint:
            options += ["--entrypoint", entrypoint]
        for key, value in (env or {}).items():
            options += ["--env", key + "=" + str(value)]
        container_id = None
        exit_code = None
        removed = False
        try:
            _, text = self.call(*(options + [image, *args]), logged=False)
            container_id = text.strip()
            item = self.inspect(container_id)
            self.assert_contract(item, 2 * 1024**3, 2, network)
            write_json("logs/" + name + "/container-inspect.json", item)
            write_json(resources, {"owner": OWNER, "name": name, "container": container_id, "status": "running"})
            code, text = self.call("start", "--attach", container_id, check=False, timeout=timeout)
            item = self.inspect(container_id)
            if item is None or item["State"]["Running"]:
                raise ProjectError("Job did not reach an exited state.")
            exit_code = item["State"]["ExitCode"]
            if code not in (0, expected_exit) or exit_code != expected_exit:
                raise ProjectError("Job failed (exit %s; expected %s). Results: %s; logs: %s" % (exit_code, expected_exit, output, log))
        finally:
            target = container_id or name
            item = self.inspect(target)
            if item is not None:
                if item["Config"].get("Labels", {}).get(OWNER_KEY) != OWNER:
                    raise ProjectError("Conflicting container preserved; cleanup ownership mismatch.")
                _, data = self.call("logs", target, check=False, logged=False)
                (log / "container.log").write_text(data)
                self.call("rm", "--force", target, timeout=90)
            removed = self.inspect(target) is None
            write_json(resources, {"owner": OWNER, "name": name, "container": target,
                                   "status": "removed" if removed else "cleanup_failed"})
            write_json("resutls/" + name + "/run-status.json", {
                "kind": "software_readiness", "scientific_results": False,
                "exit_code": exit_code, "expected_exit_code": expected_exit,
                "passed": exit_code == expected_exit and removed, "container_removed": removed,
            })
            if not removed:
                raise ProjectError("Job cleanup failed. Run the scoped cleanup command.")
        return {"run_id": name, "result_path": str(output.relative_to(ROOT)),
                "log_path": str(log.relative_to(ROOT)), "exit_code": exit_code, "container_removed": removed}

    @contextmanager
    def builder(self, image):
        name = "rocket-build-" + uuid.uuid4().hex[:12]
        journal = "logs/setup/" + name + ".json"
        write_json(journal, {"owner": OWNER, "builder": name, "status": "creating"})
        try:
            self.call("buildx", "create", "--name", name, "--driver", "docker-container",
                      "--driver-opt", "image=" + image,
                      "--driver-opt", "memory=4g", "--driver-opt", "memory-swap=4g",
                      "--driver-opt", "cpu-period=100000", "--driver-opt", "cpu-quota=200000",
                      "--driver-opt", "restart-policy=no", "--bootstrap", timeout=900)
            yield name
        finally:
            # Remove only the unique builder this invocation recorded; keep no builder state volume.
            self.call("buildx", "rm", "--force", name, check=False, timeout=90)
            remains = self.inspect("buildx_buildkit_" + name + "0")
            code, _ = self.call("volume", "inspect", "buildx_buildkit_" + name + "0_state", check=False, logged=False)
            removed = remains is None and code != 0
            write_json(journal, {"owner": OWNER, "builder": name, "status": "removed" if removed else "cleanup_failed"})
            if not removed:
                raise ProjectError("BuildKit cleanup failed; run the scoped cleanup command.")

    def cleanup(self):
        _, ids = self.call("ps", "-aq", "--filter", "label=" + OWNER_KEY + "=" + OWNER, logged=False)
        for container_id in ids.split():
            item = self.inspect(container_id)
            if item and item["Config"].get("Labels", {}).get(OWNER_KEY) == OWNER:
                name = item["Config"].get("Labels", {}).get(RUN_KEY, "recovery")
                log = folder("logs/" + name)
                _, text = self.call("logs", container_id, check=False, logged=False)
                (log / "recovery-container.log").write_text(text)
                self.call("rm", "--force", container_id)
        # Internal Compose networks carry the same repository label.
        _, networks = self.call("network", "ls", "-q", "--filter", "label=" + OWNER_KEY + "=" + OWNER, logged=False)
        for network_id in networks.split():
            self.call("network", "rm", network_id)
        for path in folder("logs/setup").glob("rocket-build-*.json"):
            record = json.loads(path.read_text())
            if record.get("owner") == OWNER and record.get("status") != "removed":
                builder = record["builder"]
                if not builder.startswith("rocket-build-") or len(builder) != len("rocket-build-") + 12:
                    raise ProjectError("Unexpected saved builder name; preserved.")
                self.call("buildx", "rm", "--force", builder, check=False, timeout=90)
                if self.inspect("buildx_buildkit_" + builder + "0"):
                    raise ProjectError("The recorded builder could not be removed.")
                write_json(str(path.relative_to(ROOT)), {"owner": OWNER, "builder": builder, "status": "removed"})
        _, remains = self.call("ps", "-aq", "--filter", "label=" + OWNER_KEY + "=" + OWNER, logged=False)
        if remains.strip():
            raise ProjectError("Some project containers remain; inspect the cleanup log.")
        print("PROJECT_CONTAINERS_REMOVED; unrelated Docker resources preserved.")
