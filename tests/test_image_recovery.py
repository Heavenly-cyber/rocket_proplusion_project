"""Cached image recovery uses simulated Docker and real local receipt files."""

from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@contextmanager
def modules(root):
    previous = sys.modules.get("host_common")
    spec = importlib.util.spec_from_file_location("host_common", SCRIPTS / "host_common.py")
    common = importlib.util.module_from_spec(spec)
    sys.modules["host_common"] = common
    try:
        spec.loader.exec_module(common)
        common.ROOT = root
        loaded = []
        for filename in ("environment.py", "worker_probe.py"):
            spec = importlib.util.spec_from_file_location("recovery_" + filename[:-3], SCRIPTS / filename)
            value = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(value)
            loaded.append(value)
        yield common, *loaded
    finally:
        if previous is None:
            sys.modules.pop("host_common", None)
        else:
            sys.modules["host_common"] = previous


def runtime_tree(root):
    files = {"pyproject.toml": b"test runtime\n", "uv.lock": b"test lock\n", "src/example.py": b"x = 1\n",
             "configs/cpu-profile.json": b"{}\n", "docker/worker.Dockerfile": b"FROM pinned\n",
             "configs/stack-selection.json": json.dumps({"dependencies": [{"name": "example", "version": "1.0"}]}).encode(),
             "scripts/worker_probe.py": (SCRIPTS / "worker_probe.py").read_bytes()}
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {"python": "3.13.16", "uv": "0.13.1", "base_images": {"buildkit": "pinned"},
            "uv_lock_sha256": "a" * 64, "llama_cpp_source_commit": "b" * 40}


class Adapter:
    def __init__(self, root, environment, present=True, bad_proof=False):
        self.root = root
        self.environment = environment
        self.present = present
        self.bad_proof = bad_proof
        self.image_ids = {environment.OBSERVED_WORKER} if present else set()
        self.calls = []
        self.cleaned = 0

    def inspect(self, image, kind=None):
        self.calls.append(("inspect", image, kind))
        return {"Id": image, "Architecture": "amd64"} if image in self.image_ids else None

    def job(self, image, args, **kwargs):
        self.calls.append(("job", image, kwargs))
        spec = json.loads(kwargs["env"]["ROCKET_WORKER_INPUTS"])
        output = self.root / "resutls/probe"
        output.mkdir(parents=True, exist_ok=True)
        (output / "worker-inputs.json").write_text(json.dumps({"status": "passed", "runtime_sha256": "invalid" if self.bad_proof else spec["runtime_sha256"]}))
        return {"result_path": "resutls/probe", "container_removed": True}

    @contextmanager
    def builder(self, image):
        try:
            yield "simulated-builder"
        finally:
            self.cleaned += 1


def test_runtime_fingerprint_tracks_app_and_lock_inputs(tmp_path):
    with modules(tmp_path) as (_, environment, _probe):
        lock = runtime_tree(tmp_path)
        first = environment.worker_specification(lock)["runtime_sha256"]
        (tmp_path / "scripts/host-new.py").write_text("host orchestration only\n")
        assert environment.worker_specification(lock)["runtime_sha256"] == first
        (tmp_path / "uv.lock").write_text("changed lock\n")
        assert environment.worker_specification(lock)["runtime_sha256"] != first


def test_observed_worker_is_reverified_before_every_adoption(tmp_path):
    with modules(tmp_path) as (_, environment, _probe):
        spec = environment.worker_specification(runtime_tree(tmp_path))
        jobs = Adapter(tmp_path, environment)
        image = environment.cached_worker(jobs, spec, "token")
        assert image["id"] == environment.OBSERVED_WORKER
        assert environment.cached_worker(jobs, spec, "token") == image
        assert len([call for call in jobs.calls if call[0] == "job"]) == 2
        assert all(call[2] == "image" for call in jobs.calls if call[0] == "inspect")
        assert json.loads((tmp_path / "tmp/setup/worker-image.json").read_text())["runtime_sha256"] == spec["runtime_sha256"]


def test_missing_image_is_not_treated_as_completed_work(tmp_path):
    with modules(tmp_path) as (_, environment, _probe):
        spec = environment.worker_specification(runtime_tree(tmp_path))
        assert environment.cached_worker(Adapter(tmp_path, environment, present=False), spec, "token") is None
        assert not (tmp_path / "tmp/setup/worker-image.json").exists()


def test_observed_manifest_identity_is_supported(tmp_path):
    with modules(tmp_path) as (_, environment, _probe):
        spec = environment.worker_specification(runtime_tree(tmp_path))
        jobs = Adapter(tmp_path, environment, present=False)
        jobs.image_ids.add(environment.OBSERVED_WORKER_MANIFEST)
        image = environment.cached_worker(jobs, spec, "token")
        assert image["id"] == environment.OBSERVED_WORKER_MANIFEST


def test_failed_worker_proof_does_not_save_adoption(tmp_path):
    with modules(tmp_path) as (common, environment, _probe):
        spec = environment.worker_specification(runtime_tree(tmp_path))
        try:
            environment.cached_worker(Adapter(tmp_path, environment, bad_proof=True), spec, "token")
        except common.ProjectError:
            pass
        else:
            raise AssertionError("An invalid worker proof was accepted.")
        assert not (tmp_path / "tmp/setup/worker-image.json").exists()


def test_worker_survives_llama_build_failure_and_is_not_built_twice(tmp_path):
    with modules(tmp_path) as (common, environment, _probe):
        lock = runtime_tree(tmp_path)
        jobs = Adapter(tmp_path, environment, present=False)
        builds = []
        def build(_jobs, builder, file, tag, pins, commit=None):
            builds.append(file)
            if "llama" in file:
                raise common.ProjectError("simulated snapshot timeout")
            image_id = "sha256:" + "c" * 64
            jobs.image_ids.add(image_id)
            return {"tag": tag, "id": image_id}
        with mock.patch.object(environment, "build", side_effect=build):
            for _ in range(2):
                try:
                    environment.ensure_images(jobs, lock)
                except common.ProjectError as error:
                    assert "snapshot timeout" in str(error)
                else:
                    raise AssertionError("The simulated llama build unexpectedly passed.")
        assert builds.count("docker/worker.Dockerfile") == 1
        assert builds.count("docker/llama.Dockerfile") == 2 and jobs.cleaned == 2


def test_probe_checks_real_files_versions_and_extra_source_files(tmp_path):
    with modules(tmp_path) as (_, environment, probe):
        spec = environment.worker_specification(runtime_tree(tmp_path))
        with mock.patch.object(probe.importlib.metadata, "version", return_value="1.0"), \
                mock.patch.object(probe.platform, "python_version", return_value="3.13.16"), \
                mock.patch.object(probe.subprocess, "check_output", return_value="uv 0.13.1\n"):
            assert probe.verify(spec, tmp_path)["status"] == "passed"
            (tmp_path / "src/unexpected.py").write_text("extra source\n")
            try:
                probe.verify(spec, tmp_path)
            except RuntimeError as error:
                assert "file set" in str(error)
            else:
                raise AssertionError("Unexpected application source was accepted.")
