"""Resume the frozen worker with a documented HTTP read-timeout correction."""
import hashlib
import html
import json
from pathlib import Path
import runpy
import sys
from datetime import datetime, timezone

import httpx

READ_TIMEOUT = 1800.0
MARKER = "<!-- ROCKET_TRANSPORT_TIMEOUT_NOTE -->"


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".pending")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "/app/completion/worker.py":
        raise SystemExit("This adapter runs only the existing frozen nozzle worker")
    output = Path("/out")
    manifest_path = output / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    adapter_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    record_path = output / "execution-overrides.json"
    if record_path.exists():
        record = json.loads(record_path.read_text())
    else:
        record = {
            "kind": "HTTP_read_timeout_only",
            "original_read_timeout_seconds": 300,
            "resumed_read_timeout_seconds": int(READ_TIMEOUT),
            "reason": "Successful CPU requests reached 289 seconds; a later request timed out twice at 300 seconds.",
            "scientific_fingerprint": manifest["fingerprint"],
            "scientific_source_commit": manifest["source_commit"],
            "generation_parameters_changed": False,
            "reference_or_scoring_changed": False,
            "existing_received_responses_replaced": False,
            "adapter_sha256": adapter_sha,
            "invocations": [],
        }
    if record["scientific_fingerprint"] != manifest["fingerprint"]:
        raise RuntimeError("Transport record belongs to another study")
    record["adapter_sha256"] = adapter_sha
    record["invocations"].append({
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "responses_already_saved": len(list((output / "responses").glob("*.json"))),
        "read_timeout_seconds": int(READ_TIMEOUT),
        "adapter_sha256": adapter_sha,
    })
    write_json(record_path, record)
    manifest["execution_overrides"] = {
        "record": "execution-overrides.json",
        "current_http_read_timeout_seconds": int(READ_TIMEOUT),
        "original_protocol_http_timeout_seconds": 300,
        "scientific_generation_and_scoring_unchanged": True,
    }
    write_json(manifest_path, manifest)

    original_client = httpx.Client

    class ResumeClient(original_client):
        def __init__(self, *args, **kwargs):
            if str(kwargs.get("base_url", "")).rstrip("/") == "http://llm:8080":
                selected = kwargs.get("timeout")
                if not isinstance(selected, httpx.Timeout):
                    raise RuntimeError("Expected the frozen worker's explicit HTTP timeout")
                kwargs["timeout"] = httpx.Timeout(
                    connect=selected.connect,
                    read=max(READ_TIMEOUT, selected.read or READ_TIMEOUT),
                    write=selected.write,
                    pool=selected.pool,
                )
            super().__init__(*args, **kwargs)

    httpx.Client = ResumeClient
    sys.argv = sys.argv[1:]
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    finally:
        httpx.Client = original_client
        note = (
            "This study resumed after HTTP read timeouts. The original transport limit was "
            "300 seconds; resumed requests allow 1800 seconds. The model, prompts, token "
            "limit, seeds, benchmark, references and scoring rules did not change. Previously "
            "received responses were retained. execution-overrides.json records the boundary."
        )
        for filename in ("TERM_PAPER.md", "RESULTS_SUMMARY.md"):
            path = output / filename
            if path.exists():
                text = path.read_text().split(MARKER, 1)[0].rstrip()
                path.write_text(text + "\n\n" + MARKER + "\n## Execution note\n\n" + note + "\n")
        report = output / "study-report.html"
        if report.exists():
            text = report.read_text().split(MARKER, 1)[0].replace("</html>", "")
            report.write_text(text + MARKER + "<h2>Execution note</h2><p>" + html.escape(note) + "</p></html>")


if __name__ == "__main__":
    main()
