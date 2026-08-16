import hashlib
import json
import os
import platform
import time
import uuid
from pathlib import Path

from .config import DEVICE_SYNC_STATE_FILE


def workspace_key(endpoint_url: str, bucket: str, prefix: str) -> str:
    identity = f"{endpoint_url}|{bucket}|{prefix}".encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def current_workspace_key() -> str | None:
    bucket = os.environ.get("R2_BUCKET", "").strip()
    endpoint = os.environ.get("R2_ENDPOINT_URL", "").strip()
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not endpoint and account_id:
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    if not bucket or not endpoint:
        return None
    prefix = os.environ.get("R2_PREFIX", "sessions").strip().strip("/") or "sessions"
    return workspace_key(endpoint, bucket, prefix)


def _device_name() -> str:
    configured = os.environ.get("PRACTICE_LAB_DEVICE_NAME", "").strip()
    return configured[:120] or platform.node()[:120] or "PracticeLab device"


def new_local_sync_state() -> dict:
    return {
        "version": 1,
        "deviceId": str(uuid.uuid4()),
        "deviceName": _device_name(),
        "sessions": {},
        "tombstones": {},
        "folders": {},
    }


def load_local_sync_state(path: Path = DEVICE_SYNC_STATE_FILE) -> dict:
    created = False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = new_local_sync_state()
        created = True
    if not isinstance(payload, dict) or not payload.get("deviceId"):
        payload = new_local_sync_state()
        created = True
    payload.setdefault("version", 1)
    payload.setdefault("deviceName", _device_name())
    if not isinstance(payload.get("sessions"), dict):
        payload["sessions"] = {}
    if not isinstance(payload.get("tombstones"), dict):
        payload["tombstones"] = {}
    if not isinstance(payload.get("folders"), dict):
        payload["folders"] = {}
    if created:
        save_local_sync_state(payload, path)
    return payload


def save_local_sync_state(state: dict, path: Path = DEVICE_SYNC_STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def record_session_deletions(
    video_ids: list[str],
    *,
    deleted_at: float | None = None,
    path: Path = DEVICE_SYNC_STATE_FILE,
) -> None:
    state = load_local_sync_state(path)
    active_workspace = current_workspace_key()
    if active_workspace and state.get("workspaceKey") != active_workspace:
        state["workspaceKey"] = active_workspace
        state["sessions"] = {}
        state["tombstones"] = {}
        state["folders"] = {}
    timestamp = float(deleted_at if deleted_at is not None else time.time())
    for video_id in video_ids:
        state["tombstones"][video_id] = {
            "deletedAt": timestamp,
            "deviceId": state["deviceId"],
        }
        state["sessions"].pop(video_id, None)
    save_local_sync_state(state, path)


def remote_revision(entry: dict | None) -> str:
    if not entry:
        return ""
    return "|".join(
        (
            str(entry.get("updatedAt") or entry.get("deletedAt") or 0),
            str(entry.get("deviceId") or ""),
            str(entry.get("digest") or ("deleted" if entry.get("deleted") else "")),
        )
    )
