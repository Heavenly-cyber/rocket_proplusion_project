"""Regression tests for explicit Docker absence and scoped builder cleanup.

An adapter supplies Docker responses; no Docker daemon is started by these tests.
"""

from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys

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
        spec = importlib.util.spec_from_file_location("inspection_jobs", SCRIPTS / "container_jobs.py")
        jobs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(jobs)
        yield common, jobs
    finally:
        if previous is None:
            sys.modules.pop("host_common", None)
        else:
            sys.modules["host_common"] = previous


def adapter(jobs, result):
    class Response(jobs.Jobs):
        def __init__(self):
            self.calls = []

        def call(self, *args, **kwargs):
            self.calls.append(args)
            return result
    return Response()


def test_missing_resource_formats_and_exact_identity(tmp_path):
    with modules(tmp_path) as (_, jobs):
        for prefix in ("Error: No such object: ", "error: no such object: ", "ERROR: NO SUCH OBJECT: "):
            assert jobs.missing_resource("[]\n" + prefix + "target\n", "target")
        assert jobs.missing_resource("Error response from daemon: No such container: target", "target", "container")
        assert jobs.missing_resource("error: no such image: target", "target", "image")
        for response in ("error: no such object: another", "error: no such object: target-extra",
                         "error: no such object: TARGET", "[]", "unrecognized failure"):
            assert not jobs.missing_resource(response, "target")
        assert not jobs.missing_resource("error: no such object: target\nCannot connect to the Docker daemon", "target")


def test_lowercase_absence_is_recorded_as_confirmed(tmp_path):
    with modules(tmp_path) as (_, jobs):
        response = "[]\nerror: no such object: target\n"
        fake = adapter(jobs, (1, response))
        assert fake.inspect("target") is None
        records = list((tmp_path / "logs/setup/docker-inspection").glob("*.json"))
        assert len(records) == 1
        record = json.loads(records[0].read_text())
        assert record["classification"] == "explicitly_absent" and record["docker_output"] == response


def test_connection_permission_and_wrong_exit_fail_closed(tmp_path):
    with modules(tmp_path) as (common, jobs):
        cases = [(1, "Cannot connect to the Docker daemon"), (1, "permission denied"),
                 (1, "error: no such object: another"), (2, "error: no such object: target"),
                 (1, "error: no such object: target\npermission denied")]
        for result in cases:
            fake = adapter(jobs, result)
            try:
                fake.inspect("target")
            except common.ProjectError as error:
                assert "Diagnostic:" in str(error) and result[1] in str(error)
            else:
                raise AssertionError("Inspection failure was mistaken for absence.")
        records = [json.loads(path.read_text()) for path in (tmp_path / "logs/setup/docker-inspection").glob("*.json")]
        assert len(records) == len(cases) and all(record["classification"] == "inspection_failed" for record in records)


def test_typed_volume_absence_formats(tmp_path):
    with modules(tmp_path) as (common, jobs):
        for response in ("[]\nError response from daemon: get state: no such volume\n",
                         "error response from daemon: no such volume: state"):
            fake = adapter(jobs, (1, response))
            assert fake.inspect("state", kind="volume") is None
            assert fake.calls == [("volume", "inspect", "state")]
        fake = adapter(jobs, (1, "error: no such container: state"))
        try:
            fake.inspect("state", kind="volume")
        except common.ProjectError:
            pass
        else:
            raise AssertionError("A different resource type established volume absence.")


def test_success_requires_one_valid_json_object(tmp_path):
    with modules(tmp_path) as (common, jobs):
        assert adapter(jobs, (0, '[{"Id":"image-id"}]')).inspect("image") == {"Id": "image-id"}
        for output in ("[]", "{}", "not JSON", "[1]", "[{},{}]"):
            try:
                adapter(jobs, (0, output)).inspect("target")
            except common.ProjectError as error:
                assert "invalid JSON" in str(error)
            else:
                raise AssertionError("An invalid inspection response was accepted.")


def builder_adapter(jobs, volume="absent"):
    class Builder(jobs.Jobs):
        def __init__(self):
            self.calls = []

        def call(self, *args, **kwargs):
            self.calls.append(args)
            if args[:2] == ("buildx", "create"):
                return 0, args[args.index("--name") + 1]
            if args[:2] == ("buildx", "rm"):
                return 0, "builder removed\n"
            if args[:2] == ("container", "inspect"):
                return 1, "[]\nerror: no such container: " + args[2] + "\n"
            if args[:2] == ("volume", "inspect"):
                if volume == "present":
                    return 0, '[{}]'
                if volume == "error":
                    return 1, "Cannot connect to the Docker daemon"
                return 1, "[]\nError response from daemon: get " + args[2] + ": no such volume\n"
            if args[0] == "ps" or args[:2] == ("network", "ls"):
                return 0, ""
            raise AssertionError("Unexpected simulated Docker command: " + repr(args))
    return Builder()


def test_builder_removal_checks_container_and_volume(tmp_path):
    with modules(tmp_path) as (_, jobs):
        fake = builder_adapter(jobs)
        with fake.builder("pinned-buildkit") as name:
            assert name.startswith("rocket-build-")
        journal = json.loads((tmp_path / "logs/setup" / (name + ".json")).read_text())
        assert journal["status"] == "removed"
        assert ("container", "inspect", "buildx_buildkit_" + name + "0") in fake.calls
        assert ("volume", "inspect", "buildx_buildkit_" + name + "0_state") in fake.calls


def test_leftover_volume_blocks_success(tmp_path):
    with modules(tmp_path) as (common, jobs):
        fake = builder_adapter(jobs, volume="present")
        name = None
        try:
            with fake.builder("pinned-buildkit") as name:
                pass
        except common.ProjectError:
            pass
        else:
            raise AssertionError("An existing state volume was reported removed.")
        journal = json.loads((tmp_path / "logs/setup" / (name + ".json")).read_text())
        assert journal["status"] == "cleanup_failed"


def test_volume_inspection_error_does_not_confirm_removal(tmp_path):
    with modules(tmp_path) as (common, jobs):
        fake = builder_adapter(jobs, volume="error")
        name = None
        try:
            with fake.builder("pinned-buildkit") as name:
                pass
        except common.ProjectError as error:
            assert "Cannot connect" in str(error)
        else:
            raise AssertionError("An unverified volume was reported removed.")
        journal = json.loads((tmp_path / "logs/setup" / (name + ".json")).read_text())
        assert journal["status"] != "removed"


def test_saved_builder_journal_recovers_idempotently(tmp_path):
    with modules(tmp_path) as (common, jobs):
        name = "rocket-build-123456abcdef"
        common.write_json("logs/setup/" + name + ".json", {"owner": jobs.OWNER, "builder": name, "status": "creating"})
        fake = builder_adapter(jobs)
        fake.cleanup()
        journal = json.loads((tmp_path / "logs/setup" / (name + ".json")).read_text())
        assert journal["status"] == "removed"
        assert ("volume", "inspect", "buildx_buildkit_" + name + "0_state") in fake.calls
        assert not any("prune" in call for call in fake.calls)
