"""A private Compose session that ends after one software-readiness request."""

import json
import os
from pathlib import Path

from container_jobs import OWNER, OWNER_KEY, RUN_KEY, run_id
from host_common import ROOT, ProjectError, folder, write_json


def available_ram():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    return 0


def probe_session(jobs, images):
    if available_ram() < 6 * 1024**3:
        raise ProjectError("Local model check needs at least 6 GiB currently available RAM. Close large apps and rerun this same stage.")
    name = run_id("llm")
    output = folder("resutls/" + name)
    log = folder("logs/" + name)
    config_directory = folder("tmp/compose/" + name)
    selected = json.loads((ROOT / "configs/stack-selection.json").read_text())
    weights = folder("models") / selected["model"]["filename"]
    if not weights.is_file() or weights.is_symlink():
        raise ProjectError("The verified GGUF model file is missing.")
    profile = json.loads((ROOT / "configs/cpu-profile.json").read_text())
    service = profile["model_service"]
    user = "%d:%d" % (os.getuid(), os.getgid())
    labels = {OWNER_KEY: OWNER, RUN_KEY: name}
    common = {"user": user, "read_only": True, "cap_drop": ["ALL"],
              "security_opt": ["no-new-privileges:true"], "restart": "no", "init": True,
              "pids_limit": 256, "tmpfs": ["/tmp:rw,nosuid,nodev,size=536870912,mode=1777"],
              "labels": labels, "networks": ["private"], "stop_grace_period": "10s"}
    model = dict(common, image=images["llama"]["id"], pull_policy="never", cpus=service["cpu_limit"],
                 mem_limit="8g", memswap_limit="8g", command=[
                     "--model", "/models/" + weights.name, "--host", "0.0.0.0", "--port", "8080",
                     "--alias", "rocket-nozzle-local", "--threads", str(service["cpu_threads"]),
                     "--threads-batch", str(service["cpu_threads"]),
                     "--ctx-size", str(service["context_tokens"]), "--parallel", "1", "--n-gpu-layers", "0",
                     "--jinja", "--chat-template-kwargs", '{"enable_thinking":false}',
                 ], volumes=[{"type": "bind", "source": str(weights.parent), "target": "/models", "read_only": True}])
    worker = dict(common, image=images["worker"]["id"], pull_policy="never", cpus=2,
                  mem_limit="2g", memswap_limit="2g", command=["probe"],
                  volumes=[{"type": "bind", "source": str(output), "target": "/out"}])
    document = {"services": {"llm": model, "worker": worker},
                "networks": {"private": {"internal": True, "labels": labels}}}
    config = config_directory / "compose.json"
    config.write_text(json.dumps(document, indent=2) + "\n")
    prefix = ["compose", "--project-name", name, "--file", str(config)]
    journal = "logs/" + name + "/resources.json"
    write_json(journal, {"owner": OWNER, "compose_project": name, "compose_file": str(config), "status": "creating"})
    exit_code = None
    removed = False
    try:
        # Inspect the containers before any model code starts.
        jobs.call(*(prefix + ["create", "llm", "worker"]), timeout=120)
        ids = {}
        for key, memory, cpus in [("llm", 8 * 1024**3, 6), ("worker", 2 * 1024**3, 2)]:
            _, identity = jobs.call(*(prefix + ["ps", "--all", "--quiet", key]), logged=False)
            ids[key] = identity.strip()
            if not ids[key]:
                raise ProjectError("Compose did not create the expected service.")
            item = jobs.inspect(ids[key])
            jobs.assert_contract(item, memory, cpus)
            write_json("logs/" + name + "/" + key + "-inspect.json", item)
        _, network_ids = jobs.call("network", "ls", "-q", "--filter", "label=com.docker.compose.project=" + name, logged=False)
        if len(network_ids.split()) != 1:
            raise ProjectError("Compose private network count differs.")
        _, network_record = jobs.call("network", "inspect", network_ids.strip(), logged=False)
        network_record = json.loads(network_record)[0]
        if not network_record["Internal"] or network_record.get("Labels", {}).get(OWNER_KEY) != OWNER:
            raise ProjectError("The model network is not internal or ownership differs.")
        write_json(journal, {"owner": OWNER, "compose_project": name, "compose_file": str(config), "containers": ids, "status": "running"})
        jobs.call(*(prefix + ["start", "llm"]), timeout=90)
        code, _ = jobs.call("start", "--attach", ids["worker"], check=False, timeout=660)
        item = jobs.inspect(ids["worker"])
        if item is None or item["State"]["Running"]:
            raise ProjectError("The model probe did not exit.")
        exit_code = item["State"]["ExitCode"]
        if code or exit_code or item["State"].get("OOMKilled"):
            raise ProjectError("Local model readiness failed. Inspect: " + str(log))
        readiness = json.loads((output / "model-readiness.json").read_text())
        if not readiness.get("passed") or readiness.get("scientific_results"):
            raise ProjectError("Invalid model readiness record.")
    finally:
        _, text = jobs.call(*(prefix + ["logs", "--no-color"]), check=False, logged=False)
        (log / "compose.log").write_text(text)
        jobs.call(*(prefix + ["down", "--remove-orphans", "--volumes", "--timeout", "10"]), check=False, timeout=120)
        _, containers = jobs.call("ps", "-aq", "--filter", "label=com.docker.compose.project=" + name, logged=False)
        _, networks = jobs.call("network", "ls", "-q", "--filter", "label=com.docker.compose.project=" + name, logged=False)
        removed = not containers.strip() and not networks.strip()
        write_json(journal, {"owner": OWNER, "compose_project": name, "compose_file": str(config), "status": "removed" if removed else "cleanup_failed"})
        write_json("resutls/" + name + "/run-status.json", {"kind": "software_readiness", "scientific_results": False,
                   "exit_code": exit_code, "passed": exit_code == 0 and removed, "containers_and_network_removed": removed})
        if not removed:
            raise ProjectError("Compose cleanup failed; run the scoped cleanup command.")
    return {"run_id": name, "result_path": str(output.relative_to(ROOT)),
            "log_path": str(log.relative_to(ROOT)), "exit_code": exit_code, "containers_and_network_removed": removed}
