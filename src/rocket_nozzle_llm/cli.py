"""Container-only software checks and pinned public model download."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import time
from pathlib import Path

import httpx

from .records import ReadinessRecord, save_record


def checksum(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def selection():
    return json.loads(Path("/app/configs/stack-selection.json").read_text())


def smoke(out):
    selected = selection()
    actual = {item["name"]: importlib.metadata.version(item["name"]) for item in selected["dependencies"]}
    for item in selected["dependencies"]:
        if actual[item["name"]] != item["version"]:
            raise RuntimeError("Installed dependency differs: " + item["name"])
    if platform.python_version() != selected["python"]["version"] or os.getuid() == 0:
        raise RuntimeError("Wrong Python version or root job user.")
    import matplotlib
    import numpy
    import pypdf
    import scipy
    import bm25s
    import pint

    # Actual imports catch binary/library problems; imports are not accuracy measurements.
    assert all((matplotlib, numpy, pypdf, scipy, bm25s, pint))
    save_record(out / "software-readiness.json", ReadinessRecord(passed=True, details={
        "python": platform.python_version(), "dependencies": actual,
        "uid": os.getuid(), "gid": os.getgid(), "backend": matplotlib.get_backend(),
    }))
    print("WORKER_READINESS_PASSED")


def download(out):
    model = selection()["model"]
    folder = Path("/models")
    destination = folder / model["filename"]
    if destination.is_symlink():
        raise RuntimeError("Model symlink preserved; use a regular file.")
    if destination.exists():
        if destination.stat().st_size != model["size_bytes"] or checksum(destination) != model["sha256"]:
            raise RuntimeError("An existing different model was preserved. Return the error output.")
        print("MODEL_ALREADY_VERIFIED")
    else:
        partial = folder / (model["filename"] + ".partial")
        # A retry starts the public transfer again; an old partial is retained separately.
        if partial.exists():
            partial.rename(folder / (partial.name + ".interrupted-" + str(time.time_ns())))
        size = 0
        value = hashlib.sha256()
        progress = 0
        try:
            with httpx.Client(follow_redirects=True, trust_env=False, timeout=httpx.Timeout(90, connect=30)) as client:
                with client.stream("GET", model["download_url"]) as response:
                    if response.status_code != 200:
                        raise RuntimeError("Public model download returned HTTP " + str(response.status_code))
                    with partial.open("xb") as stream:
                        for block in response.iter_bytes(4 * 1024 * 1024):
                            size += len(block)
                            if size > model["size_bytes"]:
                                raise RuntimeError("Public artifact exceeds the selected byte count.")
                            value.update(block)
                            stream.write(block)
                            if size - progress >= 128 * 1024 * 1024:
                                print("Model transfer: %.0f%%" % (100 * size / model["size_bytes"]), flush=True)
                                progress = size
        except httpx.HTTPError as error:
            # Do not log signed CDN redirect URLs or request headers.
            raise RuntimeError("Public model transfer failed: " + type(error).__name__) from None
        if size != model["size_bytes"] or value.hexdigest() != model["sha256"]:
            raise RuntimeError("Model byte count/checksum failed; partial file retained.")
        partial.replace(destination)
    save_record(out / "model-download.json", ReadinessRecord(passed=True, details={
        "model": model["original_model"], "revision": model["revision"],
        "quantization": model["quantization"], "filename": model["filename"],
        "bytes": model["size_bytes"], "sha256": model["sha256"], "license": model["license"],
    }))
    print("MODEL_SHA256_VERIFIED")


def probe(out):
    started = time.monotonic()
    base = "http://llm:8080"
    # No external network exists in this Compose session.
    with httpx.Client(trust_env=False, timeout=httpx.Timeout(300, connect=5)) as client:
        for _ in range(150):
            try:
                response = client.get(base + "/health")
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("Model health timeout; inspect the saved llama logs.")
        try:
            response = client.post(base + "/v1/chat/completions", json={
                "model": "rocket-nozzle-local", "stream": False,
                "messages": [{"role": "user", "content": "Reply with the single word READY."}],
                "max_tokens": 16, "seed": 17,
                "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5,
                "chat_template_kwargs": {"enable_thinking": False},
            })
            if response.status_code != 200:
                raise RuntimeError("Local inference returned HTTP " + str(response.status_code))
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError("Local inference failed: " + type(error).__name__) from None
    message = data["choices"][0]["message"]
    if not isinstance(message.get("content"), str) or not message["content"].strip():
        raise RuntimeError("Local API returned no direct-answer text.")
    if message.get("reasoning_content"):
        raise RuntimeError("Thinking output detected despite the direct-answer setting.")
    save_record(out / "model-readiness.json", ReadinessRecord(passed=True, details={
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "request_purpose": "API software check, not propulsion evaluation",
        "response": data, "thinking_enabled": False,
    }))
    print("LOCAL_LLM_READINESS_PASSED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["smoke", "download-model", "probe", "about", "fail"])
    args = parser.parse_args()
    out = Path("/out")
    if args.command == "smoke":
        smoke(out)
    elif args.command == "download-model":
        download(out)
    elif args.command == "probe":
        probe(out)
    elif args.command == "about":
        out.joinpath("PROJECT_MANIFESTO.md").write_bytes(Path("/app/docs/PROJECT_MANIFESTO.md").read_bytes())
        print("Research-gap proposal exported. Evaluation is pending Stage 04/05.")
    else:
        print("INTENTIONAL_LIFECYCLE_FAILURE")
        return 7
    return 0
