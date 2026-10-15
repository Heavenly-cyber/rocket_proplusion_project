#!/usr/bin/env python3
"""Stage 03: save, install, lock, build, verify, clean up, and publish."""

import argparse
import fcntl
import json
import os
import signal
import sys

sys.dont_write_bytecode = True

from container_jobs import Jobs
from environment import ensure_images, resolve_environment
from github_publish import publish
from host_common import ROOT, MESSAGES, SOURCE_MESSAGE, REPAIR_MESSAGE, REPAIR_FILES, REPAIR_02_MESSAGE, REPAIR_02_FILES, ProjectError, Runner, folder, resume_checkpoint, safe, save_checkpoint, sha, write_json
from host_tools import ensure_tools
from model_session import probe_session

DYNAMIC = {"configs/host-tools.lock.json", "configs/environment-lock.json", "configs/build-receipt.json",
           "docs/STAGE_03_VERIFICATION.json", "uv.lock"}


def guard(runner):
    manifesto = json.loads(safe("configs/scaffold-files.json").read_text())
    base = manifesto["base_commit"]
    if runner.git("rev-parse", "v0.2.0^{commit}") != base or runner.git("cat-file", "-t", "refs/tags/v0.2.0") != "tag":
        raise ProjectError("Stage 02 annotated tag differs from the saved base.")
    if runner.git("branch", "--show-current") != "main":
        raise ProjectError("Expected main branch; the current branch was preserved.")
    expected = {item["path"]: item["sha256"] for item in manifesto["files"]}
    for relative, digest in expected.items():
        destination = safe(relative)
        if not destination.is_file() or sha(destination.read_bytes()) != digest:
            raise ProjectError("Saved scaffold file differs; preserved: " + relative)
    tracked = set(runner.git("ls-files").splitlines())
    static = set(expected) | {"configs/scaffold-files.json"}
    if not static <= tracked or not tracked <= static | DYNAMIC:
        raise ProjectError("Unexpected tracked files; existing work preserved.")
    history = runner.git("rev-list", "--reverse", base + "..HEAD").splitlines()
    if not history:
        raise ProjectError("Save the Stage 03 ZIP scaffold before launching setup.")
    previous = base
    allowed = {REPAIR_MESSAGE: REPAIR_FILES,
               REPAIR_02_MESSAGE: REPAIR_02_FILES,
               MESSAGES["host"]: {"configs/host-tools.lock.json"},
               MESSAGES["pins"]: {"configs/environment-lock.json", "uv.lock"},
               MESSAGES["images"]: {"configs/build-receipt.json"},
               MESSAGES["verification"]: {"docs/STAGE_03_VERIFICATION.json"}}
    for index, commit in enumerate(history):
        parents = runner.git("rev-list", "--parents", "-n", "1", commit).split()
        message = runner.git("show", "-s", "--format=%s", commit)
        if parents[1:] != [previous]:
            raise ProjectError("Unexpected Git ancestry; no modifications performed.")
        paths = set(runner.git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines())
        if index == 0:
            if message != SOURCE_MESSAGE or not paths <= static:
                raise ProjectError("The first Stage 03 source checkpoint differs.")
        elif message not in allowed or not paths <= allowed[message]:
            raise ProjectError("This Stage 03 launcher does not apply to later/unrelated commits.")
        elif message == REPAIR_MESSAGE and (index != 1 or paths != REPAIR_FILES):
            raise ProjectError("The terminal repair is not the expected minor source checkpoint.")
        elif message == REPAIR_02_MESSAGE and (index != 3 or paths != REPAIR_02_FILES):
            raise ProjectError("The Docker inspection repair is not the expected minor source checkpoint.")
        previous = commit
    changes = runner.git("status", "--porcelain", "--untracked-files=all")
    if changes:
        intent_path = safe("tmp/setup/write-intent.json")
        if not intent_path.is_file():
            raise ProjectError("Local Git changes preserved. Return git status before continuing.")
        intent = json.loads(intent_path.read_text())
        pending = set(intent["files"])
        if intent.get("message") not in allowed or pending != allowed[intent["message"]]:
            raise ProjectError("Unexpected pending checkpoint files; preserved.")
        for line in changes.splitlines():
            if line[3:] not in pending:
                raise ProjectError("Unrelated modifications preserved.")
    if runner.run(["git", "rev-parse", "--verify", "--quiet", "refs/tags/v0.3.0"], check=False, logged=False)[0] == 0:
        if runner.git("cat-file", "-t", "refs/tags/v0.3.0") != "tag" or runner.git("rev-parse", "v0.3.0^{commit}") != previous:
            raise ProjectError("Stage 03 tag conflict or later work preserved.")
        if not DYNAMIC <= tracked:
            raise ProjectError("Existing Stage 03 tag has no complete environment/verification receipts; preserved.")
        verified = json.loads(safe("docs/STAGE_03_VERIFICATION.json").read_text())
        if verified.get("status") != "passed" or verified.get("scientific_results") is not False or not verified.get("all_project_containers_removed"):
            raise ProjectError("Existing Stage 03 tag lacks the required passed verification evidence.")
    resume_checkpoint(runner)


def verify(jobs, images):
    worker = images["worker"]["id"]
    checks = {}
    checks["pytest"] = jobs.job(worker, ["-m", "pytest", "/app/tests", "-q"], kind="tests", entrypoint="/opt/venv/bin/python")
    checks["ruff"] = jobs.job(worker, ["check", "--no-cache", "/app/src", "/app/scripts", "/app/tests"], kind="lint", entrypoint="/opt/venv/bin/ruff")
    checks["worker"] = jobs.job(worker, ["smoke"], kind="worker")
    checks["failure_cleanup"] = jobs.job(worker, ["fail"], kind="failure-cleanup", expected_exit=7)
    checks["gap_export"] = jobs.job(worker, ["about"], kind="proposal")
    checks["model_file"] = jobs.job(worker, ["download-model"], kind="model-download", network="bridge", timeout=10800,
                                   extra_mounts=[(folder("models"), "/models", False)])
    checks["local_api"] = probe_session(jobs, images)
    jobs.cleanup()
    return checks


def local_setup(runner, verify_again=False):
    guard(runner)
    docker = ensure_tools(runner)
    jobs = Jobs(runner, docker)
    # A previous interrupted process owns no active launcher now because this command holds a lock.
    jobs.cleanup()
    locked = resolve_environment(jobs)
    images = ensure_images(jobs, locked)
    verification_path = safe("docs/STAGE_03_VERIFICATION.json")
    reuse = False
    if verification_path.exists() and not verify_again:
        previous = json.loads(verification_path.read_text())
        if previous.get("status") != "passed" or previous["uv_lock_sha256"] != locked["uv_lock_sha256"]:
            raise ProjectError("Saved verification differs; return the diagnostics.")
        saved_images = json.loads(safe("configs/build-receipt.json").read_text())["images"]
        # A clone may share image cache but lacks this checkout's actual run evidence.
        evidence = safe(previous["checks"]["local_api"]["result_path"] + "/model-readiness.json")
        reuse = images == saved_images and evidence.is_file()
    if reuse:
        # Current weights are always checksum-verified in a container, including on a resumed setup.
        model_check = jobs.job(images["worker"]["id"], ["download-model"], kind="model-recheck", network="bridge", timeout=10800,
                               extra_mounts=[(folder("models"), "/models", False)])
        write_json("logs/setup/reused-verification.json", {"status": "passed", "images": images,
                   "prior_local_evidence": previous["checks"]["local_api"]["result_path"], "current_model_check": model_check})
    else:
        checks = verify(jobs, images)
        receipt = {"schema_version": 1, "stage": "03", "status": "passed", "scientific_results": False,
                   "platform": "linux/amd64", "python": locked["python"], "uv": locked["uv"],
                   "uv_lock_sha256": locked["uv_lock_sha256"], "llama_cpp_source_commit": locked["llama_cpp_source_commit"],
                   "model_sha256": json.loads(safe("configs/stack-selection.json").read_text())["model"]["sha256"],
                   "checks": checks, "all_project_containers_removed": True,
                   "limits": "Initial Linux amd64 software readiness only; CPU runtime and answer accuracy are unmeasured."}
        tagged = runner.run(["git", "rev-parse", "--verify", "--quiet", "refs/tags/v0.3.0"], check=False, logged=False)[0] == 0
        if tagged:
            write_json("logs/setup/reverification.json", receipt)
        else:
            save_checkpoint(runner, {"docs/STAGE_03_VERIFICATION.json": receipt}, MESSAGES["verification"])
    jobs.cleanup()
    guard(runner)
    if runner.run(["git", "rev-parse", "--verify", "--quiet", "refs/tags/v0.3.0"], check=False, logged=False)[0]:
        runner.run(["git", "tag", "-a", "v0.3.0", "-m", "Stage 03: locked containers, verified local model, scoped cleanup"])
    if runner.git("status", "--porcelain", "--untracked-files=all"):
        raise ProjectError("The verified checkpoint is not clean.")
    if runner.git("rev-parse", "v0.3.0^{commit}") != runner.git("rev-parse", "HEAD"):
        raise ProjectError("Stage 03 tag differs from the verified HEAD; existing tag was preserved.")
    print("STAGE_03_LOCAL_READY")
    print("Project:", ROOT)
    print("Commit:", runner.git("rev-parse", "HEAD"))
    print("Tag: v0.3.0")
    print("Working tree: clean")
    print("Scientific processing: not started; software readiness only")
    print("Containers: removed; installed Docker service and image/model cache retained")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "verify", "about", "doctor", "cleanup", "publish", "check"])
    parser.add_argument("--local-only", action="store_true", help="Complete local setup; leave GitHub publication pending.")
    args = parser.parse_args()
    if os.getuid() == 0 and args.command != "check":
        print("Run as your normal user, without sudo before python3.", file=sys.stderr)
        return 1
    lock_path = folder("logs/setup") / "project-command.lock"
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another project command is active; no second job was started.", file=sys.stderr)
            return 1
        runner = Runner()
        def stop(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        try:
            if args.command in {"setup", "verify"}:
                local_setup(runner, verify_again=args.command == "verify")
                if not args.local_only:
                    publish(runner)
                    print("STAGE_03_SAVED_AND_PUBLISHED")
                    print("NEXT_STAGE_PENDING: return this output before Stage 04")
                else:
                    print("GITHUB_PENDING: run python3 scripts/project.py publish to complete Stage 03")
            elif args.command in {"check", "publish"}:
                guard(runner)
                if args.command == "publish":
                    publish(runner)
                    print("STAGE_03_SAVED_AND_PUBLISHED")
                    print("NEXT_STAGE_PENDING: return this output before Stage 04")
                else:
                    print("STAGE_03_SOURCE_CHECKPOINT_VALID")
            else:
                guard(runner)
                jobs = Jobs(runner, ensure_tools(runner, install=False))
                if args.command == "cleanup":
                    jobs.cleanup()
                elif args.command == "doctor":
                    jobs.call("version")
                    jobs.call("compose", "version")
                    print("Source files and host versions match; full software checks use verify.")
                else:
                    locked = resolve_environment(jobs)
                    images = ensure_images(jobs, locked)
                    report = jobs.job(images["worker"]["id"], ["about"], kind="proposal")
                    print("Manifesto:", ROOT / report["result_path"] / "PROJECT_MANIFESTO.md")
            return 0
        except (ProjectError, OSError, ValueError, KeyError, KeyboardInterrupt) as error:
            reason = "Interrupted; current container cleanup was attempted." if isinstance(error, KeyboardInterrupt) else str(error)
            with runner.log.open("a", encoding="utf-8") as stream:
                stream.write("STAGE_03_PENDING: " + reason + "\n")
            print("STAGE_03_PENDING: " + reason, file=sys.stderr)
            print("Saved commits and downloads were retained. Log: " + str(runner.log), file=sys.stderr)
            print("Return this output; remain in Stage 03. Rerun the same ZIP to resume.", file=sys.stderr)
            return 130 if isinstance(error, KeyboardInterrupt) else 1


if __name__ == "__main__":
    raise SystemExit(main())
