"""Resolve pins inside the temporary bootstrap container; never run on the host."""

import hashlib
import json
import platform
import re
import subprocess
import urllib.request
from pathlib import Path


def main():
    if platform.python_version() != "3.13.16":
        raise RuntimeError("The selected Python image does not contain Python 3.13.16.")
    version = subprocess.check_output(["uv", "--version"], text=True).split()[1]
    if version != "0.13.1":
        raise RuntimeError("The selected uv image does not contain uv 0.13.1.")
    selection = json.loads(Path("/input/configs/stack-selection.json").read_text())
    url = "https://api.github.com/repos/ggml-org/llama.cpp/git/ref/tags/" + selection["llama_cpp"]["release"]
    for _ in range(4):
        request = urllib.request.Request(url, headers={"User-Agent": "RocketNozzle-LLM/0.3"})
        with urllib.request.urlopen(request, timeout=60) as response:
            record = json.load(response)
        obj = record["object"]
        if obj["type"] == "commit":
            commit = obj["sha"]
            break
        if obj["type"] != "tag":
            raise RuntimeError("The release ref does not resolve to a source commit.")
        url = obj["url"]
        if not url.startswith("https://api.github.com/repos/ggml-org/llama.cpp/git/tags/"):
            raise RuntimeError("Unexpected release tag API URL.")
    else:
        raise RuntimeError("Too many annotated-tag levels.")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or commit != "d81235049384534c167caea52b85a694f6103d14":
        raise RuntimeError("Release source differs from the reviewed Stage 02 release.")
    project = Path("/work/pyproject.toml")
    project.write_bytes(Path("/input/pyproject.toml").read_bytes())
    subprocess.run(["uv", "lock", "--python", "/usr/local/bin/python"], check=True, cwd="/work")
    lock = Path("/work/uv.lock").read_bytes()
    Path("/out/uv.lock").write_bytes(lock)
    Path("/out/resolver.json").write_text(json.dumps({
        "python": platform.python_version(), "uv": version,
        "llama_cpp_source_commit": commit, "uv_lock_sha256": hashlib.sha256(lock).hexdigest(),
    }, indent=2) + "\n")
    print("CONTAINER_PINS_RESOLVED")


if __name__ == "__main__":
    main()
