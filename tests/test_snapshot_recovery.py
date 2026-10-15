"""Exercise package retries without running APT or contacting a network."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

DOCKER = Path(__file__).resolve().parents[1] / "docker"
SOURCES = b"""Types: deb
URIs: https://snapshot.debian.org/archive/debian/20261014T000000Z/
Suites: trixie trixie-updates
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
Check-Valid-Until: no

Types: deb
URIs: https://snapshot.debian.org/archive/debian-security/20261014T000000Z/
Suites: trixie-security
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
Check-Valid-Until: no
"""


def module():
    spec = importlib.util.spec_from_file_location("snapshot_installer", DOCKER / "install_snapshot.py")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def exercise(tmp_path, codes, alternate=False):
    value = module()
    source = tmp_path / "debian.sources"
    source.write_bytes(SOURCES.replace(value.PRIMARY.encode(), value.ALTERNATE.encode()) if alternate else SOURCES)
    receipt = tmp_path / "receipt.json"
    calls = []
    replies = iter(codes)

    def execute(arguments, timeout):
        calls.append((arguments, timeout, source.read_bytes()))
        return next(replies)

    return value, source, receipt, calls, execute


def test_primary_success_requires_a_complete_update(tmp_path):
    value, source, receipt, calls, execute = exercise(tmp_path, [0, 0])
    result = value.install("runtime", source, receipt, execute)
    assert result["endpoint"] == value.PRIMARY and len(calls) == 2
    assert "--error-on=any" in calls[0][0] and "libgomp1" in calls[1][0]
    assert json.loads(receipt.read_text())["status"] == "passed"


def test_failed_metadata_skips_install_and_tries_same_snapshot_elsewhere(tmp_path):
    value, source, receipt, calls, execute = exercise(tmp_path, [100, 0, 0])
    result = value.install("runtime", source, receipt, execute)
    assert len(calls) == 3 and "update" in calls[1][0] and "install" in calls[2][0]
    assert result["attempts"][0]["install_exit"] is None and result["endpoint"] == value.ALTERNATE
    canonical = calls[2][2].replace(value.ALTERNATE.encode(), value.PRIMARY.encode())
    assert canonical == SOURCES


def test_package_transfer_failure_retries_against_authenticated_alternate(tmp_path):
    value, source, receipt, calls, execute = exercise(tmp_path, [0, 100, 0, 0])
    result = value.install("compiler", source, receipt, execute)
    assert len(calls) == 4 and result["attempts"][0]["install_exit"] == 100
    assert result["snapshot"] == "20261014T000000Z"
    assert "Acquire::Retries=2" in calls[0][0] and "Acquire::https::Timeout=30" in calls[0][0]
    assert "Signed-By:" in calls[-1][2].decode() and "Check-Valid-Until: no" in calls[-1][2].decode()


def test_two_failed_endpoints_do_not_create_a_success_receipt(tmp_path):
    value, source, receipt, calls, execute = exercise(tmp_path, [124, 100])
    try:
        value.install("runtime", source, receipt, execute)
    except RuntimeError as error:
        assert "Both pinned Debian snapshot endpoints failed" in str(error)
    else:
        raise AssertionError("An unavailable archive produced a success receipt.")
    assert len(calls) == 2 and not receipt.exists()


def test_modified_sources_are_preserved_before_any_package_command(tmp_path):
    value, source, receipt, calls, execute = exercise(tmp_path, [])
    source.write_bytes(SOURCES.replace(b"20261014T000000Z", b"20261015T000000Z"))
    original = source.read_bytes()
    try:
        value.install("runtime", source, receipt, execute)
    except ValueError:
        pass
    else:
        raise AssertionError("An unreviewed archive date was used.")
    assert not calls and source.read_bytes() == original and not receipt.exists()


def test_inherited_alternate_and_source_identity_are_supported(tmp_path):
    value, source, receipt, calls, execute = exercise(tmp_path, [0, 0], alternate=True)
    assert hashlib.sha256(SOURCES).hexdigest() == value.SOURCE_SHA256
    result = value.install("compiler", source, receipt, execute)
    assert result["endpoint"] == value.ALTERNATE and len(calls) == 2


def test_bounded_command_timeout_terminates_its_process(tmp_path):
    value = module()
    pid_file = tmp_path / "pid"
    code = "import os,time; from pathlib import Path; Path(" + repr(str(pid_file)) + ").write_text(str(os.getpid())); time.sleep(30)"
    assert value.run_command([sys.executable, "-c", code], timeout=0.4) == 124
    import os
    try:
        os.kill(int(pid_file.read_text()), 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError("Timed-out package-style process remains alive.")


def test_compiler_depends_on_runtime_downloads_and_keeps_the_snapshot(tmp_path):
    text = (DOCKER / "llama.Dockerfile").read_text()
    assert "FROM ${PYTHON_IMAGE} AS runtime" in text and "FROM runtime AS compiler" in text
    assert text.count("COPY docker/debian.sources") == 1
    assert "FROM runtime\n" in text
    assert "--role runtime" in text and "--role compiler" in text
