"""Host orchestration only: paths, saved checkpoints, and child processes."""

import codecs
import hashlib
import json
import os
import queue
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MESSAGE = "feat: save Stage 03 container scaffold and recovery commands"
REPAIR_MESSAGE = "fix: preserve terminal access for Stage 03 sudo commands"
REPAIR_FILES = {
    "scripts/host_common.py", "scripts/project.py", "configs/scaffold-files.json",
    "tests/test_terminal_runner.py", "docs/STAGE_03_REPAIR_01.md",
    "docs/STAGE_03_MANUAL.md", "README.md",
}
REPAIR_02_MESSAGE = "fix: verify Docker cleanup and preserve SSH origin"
REPAIR_02_FILES = {
    "scripts/host_common.py", "scripts/project.py", "scripts/container_jobs.py",
    "scripts/github_publish.py", "configs/scaffold-files.json",
    "tests/test_docker_inspection.py", "tests/test_github_remote.py",
    "docs/STAGE_03_REPAIR_02.md", "docs/STAGE_03_MANUAL.md", "README.md",
}
REPAIR_03_MESSAGE = "fix: resume pinned snapshot builds and reuse verified worker"
REPAIR_03_FILES = {
    "scripts/host_common.py", "scripts/project.py", "scripts/environment.py", "scripts/worker_probe.py",
    "docker/llama.Dockerfile", "docker/install_snapshot.py", "configs/scaffold-files.json",
    "tests/test_snapshot_recovery.py", "tests/test_image_recovery.py",
    "docs/STAGE_03_REPAIR_03.md", "docs/PRESENTATION_ALIGNMENT.md",
    "docs/requirements/final-presentation-guidelines.pdf", "docs/STAGE_03_MANUAL.md", "README.md",
}
MESSAGES = {
    "host": "build: save verified host tool versions",
    "pins": "build: freeze container digests source revision and uv lock",
    "images": "build: save container image identities and compiler receipts",
    "verification": "test: save Stage 03 container and local model verification",
}


class ProjectError(Exception):
    pass


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(relative):
    path = ROOT / relative
    if path.is_relative_to(ROOT) is False or ".." in Path(relative).parts:
        raise ProjectError("Unsafe project path.")
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ProjectError("Symbolic-link path preserved: " + str(parent))
        if parent == ROOT:
            break
    return path


def folder(relative):
    path = safe(relative)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(relative, data):
    path = safe(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    work = folder("tmp/atomic") / (sha(relative.encode()) + "-" + stamp())
    with work.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")
    os.replace(work, path)


class Runner:
    def __init__(self):
        self.log = folder("logs/setup") / ("stage03_" + stamp() + ".log")

    def run(self, args, *, check=True, timeout=300, logged=True, interactive=False):
        if interactive:
            result = subprocess.run(args, cwd=ROOT, check=False)
            if check and result.returncode:
                raise ProjectError("Interactive command did not complete: " + args[0])
            return result.returncode
        if logged:
            with self.log.open("a", encoding="utf-8") as stream:
                stream.write("COMMAND " + json.dumps(args) + "\n")
        # sudo reads credentials from the controlling terminal, not from our output pipe.
        # A new session loses that terminal and also changes tty-scoped sudo timestamps.
        detached = Path(args[0]).name != "sudo"
        process = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=detached)
        lines = queue.Queue()

        def reader():
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            while block := process.stdout.read1(4096):
                lines.put(decoder.decode(block))
            final = decoder.decode(b"", final=True)
            if final:
                lines.put(final)
            lines.put(None)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        output = ""
        started = time.monotonic()
        heartbeat = started
        ended = False
        try:
            while not ended or process.poll() is None:
                if time.monotonic() - started > timeout:
                    raise ProjectError("Command timed out: " + args[0])
                try:
                    line = lines.get(timeout=0.2)
                    if line is None:
                        ended = True
                    else:
                        output = (output + line)[-131072:]
                        if logged:
                            print(line, end="", flush=True)
                            with self.log.open("a", encoding="utf-8") as stream:
                                stream.write(line)
                except queue.Empty:
                    pass
                if logged and time.monotonic() - heartbeat > 30:
                    print("Still running:", Path(args[0]).name, flush=True)
                    heartbeat = time.monotonic()
            code = process.wait()
        except BaseException:
            try:
                if detached:
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    # This child shares our foreground process group; never kill that group.
                    process.terminate()
                process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    if detached:
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except ProcessLookupError:
                    pass
                process.wait()
            raise
        if check and code:
            raise ProjectError("Command failed (exit %d): %s. Log: %s" % (code, args[0], self.log))
        return code, output

    def git(self, *args, check=True):
        return self.run(["git", "-C", str(ROOT), *args], check=check, logged=False)[1].rstrip("\r\n")


def commit_files(runner, paths, message):
    """Never absorb other changes; journal/adoption checks precede this call."""
    changed = runner.git("status", "--porcelain", "--untracked-files=all", "--", *paths)
    other = runner.git("status", "--porcelain", "--untracked-files=all", "--", ".", *[":(exclude)" + p for p in paths])
    if other:
        raise ProjectError("Unrelated Git changes preserved; checkpoint cannot be saved.")
    if changed:
        runner.run(["git", "add", "--", *paths])
        runner.run(["git", "commit", "-m", message])
    if runner.git("status", "--porcelain", "--untracked-files=all"):
        raise ProjectError("Checkpoint is not clean; Git hooks or local edits were preserved.")
    return runner.git("rev-parse", "HEAD")


def save_checkpoint(runner, files, message):
    """Save byte-exact write intentions before adopting tracked generated files."""
    intent_path = safe("tmp/setup/write-intent.json")
    if intent_path.exists():
        resume_checkpoint(runner)
    records = {}
    for relative, data in files.items():
        if isinstance(data, dict):
            data = (json.dumps(data, indent=2, allow_nan=False) + "\n").encode()
        destination = safe(relative)
        folder("tmp/checkpoints")
        staged = safe("tmp/checkpoints/" + sha(data))
        if staged.exists() and staged.read_bytes() != data:
            raise ProjectError("Checkpoint staging conflict; preserved.")
        if not staged.exists():
            staged.write_bytes(data)
        records[relative] = {"sha256": sha(data), "staged_path": str(staged.relative_to(ROOT)),
                             "previous_sha256": sha(destination.read_bytes()) if destination.exists() else None}
    write_json("tmp/setup/write-intent.json", {"files": records, "message": message})
    resume_checkpoint(runner)


def resume_checkpoint(runner):
    path = safe("tmp/setup/write-intent.json")
    if not path.exists():
        return
    record = json.loads(path.read_text())
    if record["message"] not in MESSAGES.values():
        raise ProjectError("Unknown checkpoint intent; preserved.")
    allowed = {
        MESSAGES["host"]: {"configs/host-tools.lock.json"},
        MESSAGES["pins"]: {"uv.lock", "configs/environment-lock.json"},
        MESSAGES["images"]: {"configs/build-receipt.json"},
        MESSAGES["verification"]: {"docs/STAGE_03_VERIFICATION.json"},
    }
    if set(record["files"]) != allowed[record["message"]]:
        raise ProjectError("Unexpected generated file set; preserved.")
    for relative, item in record["files"].items():
        staged = safe(item["staged_path"])
        if not staged.is_relative_to(safe("tmp/checkpoints")) or not staged.is_file() or sha(staged.read_bytes()) != item["sha256"]:
            raise ProjectError("Incomplete saved checkpoint bytes; preserved.")
        destination = safe(relative)
        current = sha(destination.read_bytes()) if destination.is_file() else None
        if current not in {item["previous_sha256"], item["sha256"]}:
            raise ProjectError("Edited generated checkpoint preserved: " + relative)
    for relative, item in record["files"].items():
        destination = safe(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = folder("tmp/atomic") / (sha(relative.encode()) + "-" + stamp())
        with temporary.open("xb") as stream:
            stream.write(safe(item["staged_path"]).read_bytes())
        os.replace(temporary, destination)
    commit_files(runner, sorted(record["files"]), record["message"])
    path.unlink()
