"""Real Linux PTY regression checks using harmless fixtures named sudo.

These tests never invoke sudo, install a package, or use a real credential.
They also run in the restricted worker before the Stage 03 major tag.
"""

import json
import os
import pty
import select
import signal
import sys
import time
from pathlib import Path

COMMON = Path(__file__).resolve().parents[1] / "scripts" / "host_common.py"


def _pty_command(arguments, *, send=None, markers=(), timeout=12):
    pid, master = pty.fork()
    if pid == 0:
        os.execv(arguments[0], arguments)
    transcript = bytearray()
    status = None
    sent = False
    stream_ended = False
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.05)
            if ready:
                try:
                    block = os.read(master, 65536)
                except OSError:
                    block = b""
                if block:
                    transcript.extend(block)
                else:
                    stream_ended = True
            if send is not None and not sent and all(marker in transcript for marker in markers):
                os.write(master, send)
                sent = True
            if status is None:
                returned, state = os.waitpid(pid, os.WNOHANG)
                if returned:
                    status = state
            if status is not None and (not ready or stream_ended):
                break
        if status is None:
            raise AssertionError("PTY child timed out; terminal regression failed.")
        assert os.waitstatus_to_exitcode(status) == 0, transcript.decode("utf-8", "replace")
        return transcript.decode("utf-8", "replace")
    finally:
        if status is None:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)
        os.close(master)


def _shim(root, name, body):
    path = root / name
    path.write_text("#!" + sys.executable + "\n" + body)
    # Fixtures are input data interpreted by the installed Python executable.
    # They deliberately have no execute bits and work on restricted /tmp.
    path.chmod(0o600)
    return path


def _runner_code(root, arguments, *, logged=True, timeout=5, expect_timeout=False):
    fixture_arguments = [str(arg) for arg in arguments]
    code = (
        "import importlib.util,json,sys; from pathlib import Path; "
        "spec=importlib.util.spec_from_file_location('terminal_common'," + repr(str(COMMON)) + "); "
        "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
        "module.ROOT=Path(" + repr(str(root)) + "); runner=module.Runner();\n"
    )
    # Runner still sees the original argv[0] and selects its real sudo/ordinary
    # session policy. Only the final exec target is adapted for this fixture;
    # every Popen option, including start_new_session, is passed unchanged.
    code += (
        "fixture_arguments=" + repr(fixture_arguments) + "\n"
        "original_popen=module.subprocess.Popen\n"
        "def interpret_fixture(argv,**options):\n"
        "    assert argv==fixture_arguments, 'Unexpected fixture launch'\n"
        "    return original_popen([sys.executable,'-B',*argv],**options)\n"
        "module.subprocess.Popen=interpret_fixture\n"
    )
    action = "runner.run(" + repr(fixture_arguments) + ",logged=" + repr(logged) + ",timeout=" + repr(timeout) + ")"
    if expect_timeout:
        code += "try:\n    " + action + "\nexcept module.ProjectError:\n    print('LAUNCHER_ALIVE_AFTER_TIMEOUT',flush=True)\nelse:\n    raise AssertionError('Timeout did not occur')\n"
    else:
        code += "result=" + action + "; print('CAPTURED_RESULT='+json.dumps(result),flush=True)\n"
    return code


def test_sudo_style_input_uses_terminal_and_is_not_logged(tmp_path):
    shim = _shim(tmp_path, "sudo", """import getpass, os
fd=os.open('/dev/tty',os.O_RDWR)
assert os.getpgrp()==os.tcgetpgrp(fd)
os.close(fd)
print('UNTERMINATED_OUTPUT',end='',flush=True)
assert getpass.getpass('INPUT_ON_TTY: ')=='not-a-real-password'
print('\\nTTY_INPUT_OK',flush=True)
""")
    transcript = _pty_command([sys.executable, "-B", "-c", _runner_code(tmp_path, [shim])],
                              send=b"not-a-real-password\n",
                              markers=(b"UNTERMINATED_OUTPUT", b"INPUT_ON_TTY:"))
    assert "TTY_INPUT_OK" in transcript and "not-a-real-password" not in transcript
    logs = list((tmp_path / "logs/setup").glob("stage03_*.log"))
    assert len(logs) == 1
    text = logs[0].read_text()
    assert "TTY_INPUT_OK" in text and "not-a-real-password" not in text
    assert "UNTERMINATED_OUTPUT" in text


def test_sudo_style_inspection_retains_captured_json(tmp_path):
    shim = _shim(tmp_path, "sudo", """import json,os
fd=os.open('/dev/tty',os.O_RDWR)
print(json.dumps({'terminal':os.isatty(fd),'foreground':os.getpgrp()==os.tcgetpgrp(fd)}))
os.close(fd)
""")
    transcript = _pty_command([sys.executable, "-B", "-c", _runner_code(tmp_path, [shim], logged=False)])
    result_line = next(line for line in transcript.splitlines() if line.startswith("CAPTURED_RESULT="))
    code, output = json.loads(result_line.split("=", 1)[1])
    assert code == 0 and json.loads(output) == {"terminal": True, "foreground": True}


def test_sudo_style_timeout_does_not_kill_launcher(tmp_path):
    pid_file = tmp_path / "timed-out.pid"
    shim = _shim(tmp_path, "sudo", "import os,time; from pathlib import Path; Path(" + repr(str(pid_file)) + ").write_text(str(os.getpid())); time.sleep(30)\n")
    transcript = _pty_command([sys.executable, "-B", "-c", _runner_code(tmp_path, [shim], timeout=0.5, expect_timeout=True)])
    assert "LAUNCHER_ALIVE_AFTER_TIMEOUT" in transcript
    pid = int(pid_file.read_text())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError("Timed-out sudo-style child was left alive.")


def test_detached_job_timeout_still_removes_its_process_group(tmp_path):
    pid_file = tmp_path / "group-pids.json"
    body = """import json,os,signal,subprocess,sys,time
from pathlib import Path
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
def stop(signum,frame):
    child.terminate()
    child.wait(timeout=2)
    raise SystemExit(0)
signal.signal(signal.SIGTERM,stop)
Path(PID_FILE).write_text(json.dumps([os.getpid(),child.pid]))
time.sleep(30)
""".replace("PID_FILE", repr(str(pid_file)))
    shim = _shim(tmp_path, "ordinary-job", body)
    transcript = _pty_command([sys.executable, "-B", "-c", _runner_code(tmp_path, [shim], timeout=0.5, expect_timeout=True)])
    assert "LAUNCHER_ALIVE_AFTER_TIMEOUT" in transcript
    for pid in json.loads(pid_file.read_text()):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError("Detached test process was left alive.")
