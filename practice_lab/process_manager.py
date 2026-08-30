from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Iterator, Sequence


_LOCK = threading.RLock()
_RUNNING: dict[str, subprocess.Popen] = {}
_CONTEXT = threading.local()


@contextlib.contextmanager
def job_process_context(job_id: str) -> Iterator[None]:
    previous = getattr(_CONTEXT, "job_id", None)
    _CONTEXT.job_id = job_id
    try:
        yield
    finally:
        _CONTEXT.job_id = previous


def current_job_id() -> str | None:
    return getattr(_CONTEXT, "job_id", None)


def _process_group_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def register_process(job_id: str | None, process: subprocess.Popen) -> None:
    if not job_id:
        return
    with _LOCK:
        _RUNNING[job_id] = process


def unregister_process(job_id: str | None, process: subprocess.Popen) -> None:
    if not job_id:
        return
    with _LOCK:
        if _RUNNING.get(job_id) is process:
            _RUNNING.pop(job_id, None)


def running_process(job_id: str) -> subprocess.Popen | None:
    with _LOCK:
        return _RUNNING.get(job_id)


def terminate_process(process: subprocess.Popen, *, grace_seconds: float = 5) -> None:
    if process.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=max(1, grace_seconds),
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        if process.poll() is None:
            process.kill()


def start_process(command: Sequence[str], *, job_id: str | None = None, **kwargs) -> subprocess.Popen:
    effective_job_id = job_id or current_job_id()
    process = subprocess.Popen(command, **_process_group_kwargs(), **kwargs)
    register_process(effective_job_id, process)
    return process


def run_process(
    command: Sequence[str],
    *,
    job_id: str | None = None,
    timeout: float | None = None,
    check: bool = False,
    capture_output: bool = False,
    text: bool = False,
    encoding: str | None = None,
    errors: str | None = None,
    cwd: str | os.PathLike[str] | None = None,
) -> subprocess.CompletedProcess:
    effective_job_id = job_id or current_job_id()
    stdout = subprocess.PIPE if capture_output else None
    stderr = subprocess.PIPE if capture_output else None
    process = start_process(
        command,
        job_id=effective_job_id,
        stdout=stdout,
        stderr=stderr,
        text=text,
        encoding=encoding,
        errors=errors,
        cwd=cwd,
    )
    try:
        try:
            output, error = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_process(process)
            output, error = process.communicate()
            raise subprocess.TimeoutExpired(command, timeout, output=output, stderr=error)
    finally:
        unregister_process(effective_job_id, process)
    completed = subprocess.CompletedProcess(command, process.returncode, output, error)
    if check and completed.returncode:
        raise subprocess.CalledProcessError(
            completed.returncode,
            command,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return completed
