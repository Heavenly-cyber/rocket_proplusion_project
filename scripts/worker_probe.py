"""Check a cached worker's immutable runtime inputs in an offline worker job."""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess


def verify(specification, app=Path("/app")):
    versions = {name: importlib.metadata.version(name) for name in specification["dependencies"]}
    if versions != specification["dependencies"]:
        raise RuntimeError("Cached worker dependency versions differ from the selection.")
    if platform.python_version() != specification["python"]:
        raise RuntimeError("Cached worker Python differs from the locked interpreter.")
    uv_version = subprocess.check_output(["/usr/local/bin/uv", "--version"], text=True).split()[1]
    if uv_version != specification["uv"]:
        raise RuntimeError("Cached worker uv differs from the lock.")
    actual_source = {path.relative_to(app).as_posix() for path in (app / "src").rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts}
    if actual_source != {name for name in specification["files"] if name.startswith("src/")}:
        raise RuntimeError("Cached worker source file set differs from the checkout.")
    for name, digest in specification["files"].items():
        if hashlib.sha256((app / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Cached worker runtime input differs: " + name)
    return {"status": "passed", "python": specification["python"], "uv": uv_version,
            "dependencies": versions, "runtime_sha256": specification["runtime_sha256"],
            "verified_files": specification["files"], "scientific_results": False}


def main():
    result = verify(json.loads(os.environ["ROCKET_WORKER_INPUTS"]))
    Path("/out/worker-inputs.json").write_text(json.dumps(result, indent=2) + "\n")
    print("CACHED_WORKER_INPUTS_VERIFIED", flush=True)


if __name__ == "__main__":
    main()
