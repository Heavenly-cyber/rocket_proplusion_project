"""Mount-policy checks use text metadata and never probe private directories."""

import importlib.util
from pathlib import Path

import pytest


def _policy():
    source = Path(__file__).resolve().parents[1] / "scripts/container_isolation.py"
    spec = importlib.util.spec_from_file_location("mount_policy", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(target, index=20):
    return f"{index} 1 0:42 / {target} rw,nosuid - tmpfs tmpfs rw\n"


ROOT = "1 0 0:1 / / ro - overlay overlay ro\n"


@pytest.mark.parametrize("target", [
    "/root", "/root/.config", "/root/.config/gh", "/root/.config/gh/hosts.yml",
    "/root/.ssh", "/root/.ssh/id_ed25519", "/var", "/var/run/docker.sock",
    "/run/docker.sock", "/app", "/app/.git", "/app/.git/config", "/app/.env",
    "/models", "/models/model.gguf", r"/root/.config/gh/cache\040entry",
])
def test_sensitive_mount_and_ancestor_are_detected(target):
    policy = _policy()
    expected = target.replace(r"\040", " ")
    assert policy.sensitive_mounts(ROOT + _record(target)) == (expected,)


def test_normal_root_readonly_code_and_job_mounts_are_allowed():
    text = ROOT + "".join(_record(target, index) for index, target in enumerate([
        "/tmp", "/out", "/app/scripts", "/app/tests", "/app/docker", "/dev",
        "/dev/pts", "/proc", "/sys", "/sys/fs/cgroup", "/etc/hosts",
        "/etc/hostname", "/etc/resolv.conf", "/rootless-data",
    ], 20))
    assert _policy().sensitive_mounts(text) == ()


@pytest.mark.parametrize("text", ["", "not mountinfo", "1 0 0:1 / / ro", _record("relative"),
                                        _record("/root/../tmp"), _record(r"/root\999")])
def test_malformed_metadata_does_not_pass_as_absence(text):
    with pytest.raises(ValueError):
        _policy().sensitive_mounts(text)


def test_escaped_whitespace_and_backslash_are_decoded_once():
    policy = _policy()
    assert policy.mount_points(ROOT + _record(r"/tmp/a\040b\011c\012d\134040"))[-1].as_posix() == "/tmp/a b\tc\nd\\040"


def test_overlapping_mounts_are_returned_deterministically():
    policy = _policy()
    text = ROOT + _record("/root/.ssh") + _record("/root") + _record("/root/.ssh")
    assert policy.sensitive_mounts(text) == ("/root", "/root/.ssh")
