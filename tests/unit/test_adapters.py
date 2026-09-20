import sys
import threading

import pytest

from coastmas.adapters.runtime import CLIAdapter, PythonFunctionAdapter, RunRequest
from coastmas.core.errors import CoastMASError


def test_python_only_executes_explicit_registered_handler(tmp_path):
    adapter = PythonFunctionAdapter(
        {"double": lambda inputs, parameters: {"value": inputs["value"] * 2}}
    )
    request = RunRequest(
        handler="double", inputs={"value": 3}, parameters={}, work_root=tmp_path, timeout_seconds=2
    )
    assert adapter.run(request).outputs == {"value": 6}
    with pytest.raises(CoastMASError, match="registered"):
        adapter.run(
            RunRequest(
                handler="os.system", inputs={}, parameters={}, work_root=tmp_path, timeout_seconds=2
            )
        )
    assert not list(tmp_path.iterdir())


def test_cli_uses_fixed_argv_and_collects_real_output(tmp_path):
    adapter = CLIAdapter(
        {
            "double": (
                sys.executable,
                "-c",
                "import json,sys;print(json.dumps(dict(value=int(sys.argv[1])*2)))",
                "{number}",
            )
        }
    )
    result = adapter.run(
        RunRequest(
            handler="double",
            inputs={},
            parameters={"number": 7},
            work_root=tmp_path,
            timeout_seconds=2,
        )
    )
    assert result.outputs == {"value": 14}
    assert result.exit_code == 0
    assert not list(tmp_path.iterdir())


def test_cli_reports_nonzero_exit_without_false_success(tmp_path):
    adapter = CLIAdapter({"fail": (sys.executable, "-c", "raise SystemExit(17)")})
    with pytest.raises(CoastMASError, match="17"):
        adapter.run(
            RunRequest(
                handler="fail", inputs={}, parameters={}, work_root=tmp_path, timeout_seconds=2
            )
        )
    assert not list(tmp_path.iterdir())


def test_cli_timeout_terminates_process_and_cleans_workspace(tmp_path):
    adapter = CLIAdapter({"slow": (sys.executable, "-c", "import time;time.sleep(20)")})
    with pytest.raises(CoastMASError, match="timeout"):
        adapter.run(
            RunRequest(
                handler="slow", inputs={}, parameters={}, work_root=tmp_path, timeout_seconds=0.1
            )
        )
    assert not list(tmp_path.iterdir())


def test_cli_cancel_event_propagates_to_process(tmp_path):
    event = threading.Event()
    timer = threading.Timer(0.1, event.set)
    adapter = CLIAdapter({"slow": (sys.executable, "-c", "import time;time.sleep(20)")})
    timer.start()
    try:
        with pytest.raises(CoastMASError, match="cancel"):
            adapter.run(
                RunRequest(
                    handler="slow",
                    inputs={},
                    parameters={},
                    work_root=tmp_path,
                    timeout_seconds=5,
                    cancel=event,
                )
            )
    finally:
        timer.cancel()


def test_cli_rejects_unknown_template_and_unbounded_output(tmp_path):
    adapter = CLIAdapter(
        {"large": (sys.executable, "-c", "print('x'*1000000)")}, max_output_bytes=1024
    )
    with pytest.raises(CoastMASError, match="output"):
        adapter.run(
            RunRequest(
                handler="large", inputs={}, parameters={}, work_root=tmp_path, timeout_seconds=2
            )
        )
    with pytest.raises(CoastMASError, match="registered"):
        adapter.run(
            RunRequest(
                handler="arbitrary", inputs={}, parameters={}, work_root=tmp_path, timeout_seconds=2
            )
        )


def test_child_group_is_terminated_even_after_parent_exits(tmp_path):
    import time

    marker = tmp_path / "orphan-marker"
    work = tmp_path / "work"
    child = f"import time,pathlib;time.sleep(.6);pathlib.Path({str(marker)!r}).write_text('orphan')"
    launcher = f"import subprocess,sys;subprocess.Popen([sys.executable,'-c',{child!r}])"
    adapter = CLIAdapter({"spawn": (sys.executable, "-c", launcher)})
    with pytest.raises(CoastMASError, match="timeout"):
        adapter.run(
            RunRequest(
                handler="spawn", inputs={}, parameters={}, work_root=work, timeout_seconds=0.1
            )
        )
    time.sleep(0.7)
    assert not marker.exists()


def test_python_scientific_failure_keeps_code_and_safe_diagnostic_frames(tmp_path):
    from coastmas.core.errors import ConstraintError

    def invalid(inputs, parameters):
        raise ConstraintError("vertical datum mismatch")

    adapter = PythonFunctionAdapter({"invalid": invalid})
    with pytest.raises(CoastMASError) as captured:
        adapter.run(RunRequest("invalid", {}, {}, tmp_path, 2))
    assert captured.value.code == "CONSTRAINT_ERROR"
    assert "vertical datum mismatch" in captured.value.message
    assert captured.value.details["exception_type"] == "ConstraintError"
    assert captured.value.details["frames"]
    assert not list(tmp_path.iterdir())


def test_python_unexpected_exception_does_not_expose_arguments(tmp_path):
    def invalid(inputs, parameters):
        raise RuntimeError("credential=must-not-leak")

    adapter = PythonFunctionAdapter({"invalid": invalid})
    with pytest.raises(CoastMASError) as captured:
        adapter.run(RunRequest("invalid", {}, {}, tmp_path, 2))
    assert "must-not-leak" not in str(captured.value.details)
    assert captured.value.details["exception_type"] == "RuntimeError"
