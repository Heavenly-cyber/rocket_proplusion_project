"""Real isolation and library checks, run in the bounded offline worker."""

import importlib.util
import os
from pathlib import Path

import numpy as np
import pint
import pytest
from scipy.optimize import brentq


def test_process_is_nonroot_and_has_no_capabilities():
    assert os.getuid() != 0
    fields = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
    assert int(fields["CapEff"].strip(), 16) == 0
    assert fields["NoNewPrivs"].strip() == "1"


def test_root_filesystem_is_read_only():
    with pytest.raises(OSError):
        Path("/app/should-not-exist").write_text("isolation check")


def test_no_host_secrets_or_docker_socket_are_mounted():
    source = Path(__file__).resolve().parents[1] / "scripts/container_isolation.py"
    spec = importlib.util.spec_from_file_location("container_isolation", source)
    isolation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(isolation)
    # /root is intentionally inaccessible to this nonroot process. Its mount
    # metadata is still visible; permission denial is never treated as absence.
    assert isolation.sensitive_mounts(Path("/proc/self/mountinfo").read_text()) == ()
    assert not Path("/var/run/docker.sock").exists()
    assert not Path("/run/docker.sock").exists()
    assert not Path("/app/.git").exists()
    assert not Path("/app/.env").exists()
    assert not Path("/models").exists()


def test_memory_and_pid_limits_are_present():
    memory = Path("/sys/fs/cgroup/memory.max").read_text().strip()
    pids = Path("/sys/fs/cgroup/pids.max").read_text().strip()
    assert memory != "max" and 0 < int(memory) <= 2 * 1024**3
    assert pids != "max" and 0 < int(pids) <= 256


def test_cpu_has_a_real_quota():
    quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
    assert quota != "max" and int(quota) / int(period) <= 2


def test_numerical_extension_and_units_libraries_work():
    # Library sanity, not a rocket-nozzle gold solution or research result.
    assert np.isclose(brentq(lambda x: x*x - 2, 0, 2), np.sqrt(2), atol=1e-12)
    units = pint.UnitRegistry()
    assert (1 * units.kilopascal).to("pascal").magnitude == 1000
    with pytest.raises(pint.DimensionalityError):
        (1 * units.second).to("newton")
