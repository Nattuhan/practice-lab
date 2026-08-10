from __future__ import annotations


def select_torch_device(requested: str, torch_module=None) -> str:
    if torch_module is None:
        import torch as torch_module

    if requested == "auto":
        if torch_module.cuda.is_available():
            return "cuda"
        mps = getattr(torch_module.backends, "mps", None)
        if mps is not None and mps.is_available():
            return "mps"
        return "cpu"
    if requested == "cuda" and not torch_module.cuda.is_available():
        raise RuntimeError("CUDAを利用できません。デバイスにcpuを指定してください。")
    if requested == "mps":
        mps = getattr(torch_module.backends, "mps", None)
        if mps is None or not mps.is_available():
            raise RuntimeError("Apple MPSを利用できません。デバイスにcpuを指定してください。")
    return requested


def is_acceleration_compatibility_error(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    return any(token in message for token in ("mps", "not implemented", "unsupported", "not supported"))
