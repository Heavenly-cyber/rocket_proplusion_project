"""Containerized lock resolution and fixed source/image builds."""

import json
import re
import shutil
from host_common import ROOT, MESSAGES, ProjectError, commit_files, folder, safe, sha, save_checkpoint, write_json

CANDIDATES = {"python": "python:3.13.16-slim-trixie", "uv": "ghcr.io/astral-sh/uv:0.13.1",
              "buildkit": "moby/buildkit:v0.34.0"}


def pull_pin(jobs, candidate):
    jobs.call("pull", "--platform", "linux/amd64", candidate, timeout=1800)
    item = jobs.inspect(candidate)
    pins = item.get("RepoDigests", [])
    if item.get("Architecture") != "amd64" or not pins:
        raise ProjectError("Selected container image has no amd64 digest: " + candidate)
    repository = candidate.rsplit(":", 1)[0]
    selected = next((pin for pin in pins if pin.split("@", 1)[0] == repository), pins[0])
    if not re.fullmatch(r".+@sha256:[0-9a-f]{64}", selected):
        raise ProjectError("Container image digest is incomplete.")
    return selected


def build(jobs, builder, file, tag, pins, commit=None):
    args = ["buildx", "build", "--builder", builder, "--load", "--platform", "linux/amd64",
            "--progress", "plain", "--provenance", "false", "--file", str(ROOT / file), "--tag", tag,
            "--build-arg", "PYTHON_IMAGE=" + pins["python"], "--build-arg", "UV_IMAGE=" + pins["uv"]]
    if commit:
        args += ["--build-arg", "LLAMA_COMMIT=" + commit]
    jobs.call(*(args + [str(ROOT)]), timeout=7200)
    item = jobs.inspect(tag)
    if item is None or item.get("Architecture") != "amd64":
        raise ProjectError("Built image is missing or has an unexpected platform.")
    return {"tag": tag, "id": item["Id"]}


def resolve_environment(jobs):
    runner = jobs.runner
    lock_path = safe("configs/environment-lock.json")
    uv_path = safe("uv.lock")
    if lock_path.exists():
        locked = json.loads(lock_path.read_text())
        if not uv_path.is_file() or sha(uv_path.read_bytes()) != locked["uv_lock_sha256"]:
            raise ProjectError("uv.lock differs from its saved hash; no re-resolution performed.")
        # A clean clone reuses immutable pins; never refresh version tags implicitly.
        for pin in locked["base_images"].values():
            if not re.fullmatch(r".+@sha256:[0-9a-f]{64}", pin):
                raise ProjectError("Incomplete saved base-image digest.")
            if jobs.inspect(pin) is None:
                jobs.call("pull", "--platform", "linux/amd64", pin, timeout=1800)
        commit_files(runner, ["uv.lock", "configs/environment-lock.json"], MESSAGES["pins"])
        return locked
    if uv_path.exists():
        raise ProjectError("An unexpected uv.lock was preserved; the paired environment lock is missing.")
    pending = safe("tmp/setup/pins-pending.json")
    if pending.exists():
        pins = json.loads(pending.read_text())["base_images"]
    else:
        pins = {name: pull_pin(jobs, candidate) for name, candidate in CANDIDATES.items()}
        write_json("tmp/setup/pins-pending.json", {"base_images": pins})
    # Public input copies contain no .git, credentials, models, or output directories.
    inputs = folder("tmp/setup/bootstrap-input")
    for relative in ["pyproject.toml", "configs/stack-selection.json", "scripts/container_prepare.py"]:
        destination = safe("tmp/setup/bootstrap-input/" + relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe(relative), destination)
    folder("tmp/setup/resolved-pins")
    resolved_uv = safe("tmp/setup/resolved-pins/uv.lock")
    resolved_metadata = safe("tmp/setup/resolved-pins/resolver.json")
    if not resolved_uv.is_file() or not resolved_metadata.is_file():
        with jobs.builder(pins["buildkit"]) as builder:
            bootstrap = build(jobs, builder, "docker/bootstrap.Dockerfile", "rocket-nozzle-bootstrap:" + sha(json.dumps(pins, sort_keys=True).encode())[:16], pins)
        report = jobs.job(bootstrap["id"], [], kind="resolve", network="bridge", timeout=1200,
                          extra_mounts=[(inputs, "/input", True), (folder("tmp/setup/resolver-work"), "/work", False),
                                        (folder("cache/uv"), "/cache", False)],
                          env={"UV_CACHE_DIR": "/cache", "HOME": "/tmp/home"})
        output = ROOT / report["result_path"]
        for name in ("uv.lock", "resolver.json"):
            shutil.copyfile(output / name, safe("tmp/setup/resolved-pins/" + name))
    resolver = json.loads(resolved_metadata.read_text())
    uv_bytes = resolved_uv.read_bytes()
    if sha(uv_bytes) != resolver["uv_lock_sha256"] or not re.fullmatch(r"d812350[0-9a-f]{33}", resolver["llama_cpp_source_commit"]):
        raise ProjectError("Resolved pin output failed its integrity check.")
    # A write-intent receipt lets an interruption before Git commit resume without guessing.
    locked = {"schema_version": 1, "platform": "linux/amd64", "python": resolver["python"], "uv": resolver["uv"],
              "base_images": pins, "llama_cpp_release": "v0.6.0",
              "llama_cpp_source_commit": resolver["llama_cpp_source_commit"],
              "debian_snapshot": "20261014T000000Z", "uv_lock_sha256": resolver["uv_lock_sha256"],
              "dependency_resolution": "temporary_nonroot_container"}
    save_checkpoint(runner, {"uv.lock": uv_bytes, "configs/environment-lock.json": locked}, MESSAGES["pins"])
    return locked


def ensure_images(jobs, locked):
    path = safe("configs/build-receipt.json")
    intended = safe("tmp/setup/build-receipt-intent.json")
    if path.exists():
        receipt = json.loads(path.read_text())
        # Local image IDs can change on a rebuild even with the same source. Verify content below.
        if all(jobs.inspect(value["id"]) is not None for value in receipt["images"].values()):
            commit_files(jobs.runner, ["configs/build-receipt.json"], MESSAGES["images"])
            return receipt["images"]
        if jobs.runner.run(["git", "rev-parse", "--verify", "--quiet", "refs/tags/v0.3.0"], check=False, logged=False)[0] == 0:
            # Rebuilding a clone is recorded locally, without editing the released receipt.
            print("Released source is pinned; rebuilding images missing from this Docker host.")
    token = sha((locked["uv_lock_sha256"] + locked["llama_cpp_source_commit"]).encode())[:16]
    with jobs.builder(locked["base_images"]["buildkit"]) as builder:
        images = {
            "worker": build(jobs, builder, "docker/worker.Dockerfile", "rocket-nozzle-worker:" + token, locked["base_images"]),
            "llama": build(jobs, builder, "docker/llama.Dockerfile", "rocket-nozzle-llama:" + token, locked["base_images"], locked["llama_cpp_source_commit"]),
        }
    # The binary and its dynamically loaded CPU backends are checked in an offline container.
    help_report = jobs.job(images["llama"]["id"], ["--help"], kind="llama-help", timeout=90)
    help_text = (ROOT / help_report["log_path"] / "container.log").read_text()
    if not all(flag in help_text for flag in ("--jinja", "--chat-template-kwargs", "--threads-batch", "--n-gpu-layers")):
        raise ProjectError("The built server lacks a required direct-answer/CPU flag; no model session started.")
    report = jobs.job(images["llama"]["id"], ["-c", "cat /opt/llama/SOURCE_COMMIT /opt/llama/COMPILER_PACKAGES.txt /RUNTIME_PACKAGES.txt"],
                      kind="compiler-receipt", entrypoint="/bin/sh", timeout=90)
    data = (ROOT / report["log_path"] / "container.log").read_text()
    if not data.startswith(locked["llama_cpp_source_commit"] + "\n"):
        raise ProjectError("Compiled llama source differs from the environment lock.")
    receipt = {"schema_version": 1, "source_commit": locked["llama_cpp_source_commit"],
               "uv_lock_sha256": locked["uv_lock_sha256"], "images": images,
               "compiler_and_runtime_packages": data.splitlines()[1:], "binary_check": "offline_llama_server_help_passed"}
    if path.exists() and jobs.runner.run(["git", "rev-parse", "--verify", "--quiet", "refs/tags/v0.3.0"], check=False, logged=False)[0] == 0:
        write_json("logs/setup/rebuilt-images.json", receipt)
    else:
        write_json(str(intended.relative_to(ROOT)), receipt)
        if path.exists():
            previous = json.loads(path.read_text())
            if previous["source_commit"] != receipt["source_commit"] or previous["uv_lock_sha256"] != receipt["uv_lock_sha256"]:
                raise ProjectError("Existing build receipt has different source pins; preserved.")
        save_checkpoint(jobs.runner, {"configs/build-receipt.json": receipt}, MESSAGES["images"])
    return images
