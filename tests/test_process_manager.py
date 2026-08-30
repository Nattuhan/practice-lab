import subprocess
import sys
import threading
import time

import pytest

from practice_lab.process_manager import job_process_context, run_process, running_process, terminate_process


def test_managed_process_is_terminated_on_timeout():
    started_at = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_process(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            timeout=0.1,
        )
    assert time.monotonic() - started_at < 2


def test_running_job_process_can_be_canceled_while_silent():
    finished = threading.Event()

    def run_silent_process():
        with job_process_context("silent-job"):
            run_process([sys.executable, "-c", "import time; time.sleep(10)"], timeout=10)
        finished.set()

    thread = threading.Thread(target=run_silent_process)
    thread.start()
    process = None
    for _attempt in range(100):
        process = running_process("silent-job")
        if process is not None:
            break
        time.sleep(0.01)
    assert process is not None

    terminate_process(process)
    thread.join(timeout=2)

    assert finished.is_set()
    assert not thread.is_alive()
