from __future__ import annotations

import multiprocessing
import os
import runpy
import sys
from pathlib import Path

import uvicorn

from practice_lab.app import create_app


def main() -> None:
    host = os.environ.get("PRACTICE_LAB_HOST", "127.0.0.1")
    port = int(os.environ.get("PRACTICE_LAB_PORT", "8000"))
    uvicorn.run(create_app(), host=host, port=port, log_level="info", access_log=False)


def run_frozen_python_command() -> bool:
    """Emulate the Python CLI for subprocesses launched by the frozen backend."""
    if not getattr(sys, "frozen", False) or len(sys.argv) < 2:
        return False
    if sys.argv[1] == "-m" and len(sys.argv) >= 3:
        module = sys.argv[2]
        sys.argv = [module, *sys.argv[3:]]
        runpy.run_module(module, run_name="__main__")
        return True
    script = Path(sys.argv[1])
    if script.suffix.lower() == ".py" and script.is_file():
        sys.argv = [str(script), *sys.argv[2:]]
        runpy.run_path(str(script), run_name="__main__")
        return True
    return False


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if not run_frozen_python_command():
        main()
