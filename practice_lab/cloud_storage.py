import mimetypes
import os
import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import PUBLIC_STEMS_DIR, load_env_files

STEM_NAMES = ("vocals", "drums", "bass", "other")


@dataclass(frozen=True)
class R2Config:
    bucket: str
    endpoint_url: str
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)
    public_base_url: str | None = None
    prefix: str = "sessions"
    required: bool = False
    configure_cors: bool = False


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def get_r2_config() -> R2Config | None:
    load_env_files()
    if not _truthy(os.environ.get("R2_ENABLED")):
        return None

    bucket = os.environ.get("R2_BUCKET", "").strip()
    endpoint_url = os.environ.get("R2_ENDPOINT_URL", "").strip()
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    access_key_id = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    public_base_url = os.environ.get("R2_PUBLIC_BASE_URL", "").strip().rstrip("/") or None
    prefix = os.environ.get("R2_PREFIX", "sessions").strip().strip("/") or "sessions"
    required = _truthy(os.environ.get("R2_REQUIRED"))
    configure_cors = _truthy(os.environ.get("R2_CONFIGURE_CORS"))

    if not endpoint_url and account_id:
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"

    if not all((bucket, endpoint_url, access_key_id, secret_access_key)):
        if required:
            raise RuntimeError("R2設定が不足しています")
        return None

    return R2Config(
        bucket=bucket,
        endpoint_url=endpoint_url,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        public_base_url=public_base_url,
        prefix=prefix,
        required=required,
        configure_cors=configure_cors,
    )


def build_r2_session_assets(video_id: str, config: R2Config, *, include_video: bool = True) -> dict[str, str | dict[str, str]]:
    if not config.public_base_url:
        return {}
    base = f"{config.public_base_url}/{config.prefix}/{video_id}"
    assets = {
        "result": f"{base}/session.json",
        "audio": f"{base}/audio.mp3",
    }
    if include_video:
        assets["video"] = f"{base}/video.mp4"
    stem_dir = PUBLIC_STEMS_DIR / video_id
    if all((stem_dir / f"{stem}.mp3").exists() for stem in STEM_NAMES):
        assets["stems"] = {
            stem: f"{base}/stems/{stem}.mp3"
            for stem in STEM_NAMES
        }
    return assets


def _content_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _client(config: R2Config):
    import boto3

    return boto3.client(
        service_name="s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name="auto",
    )


def test_r2_connection(config: R2Config) -> dict[str, str | bool | None]:
    _client(config).head_bucket(Bucket=config.bucket)
    viewer_url = f"{config.public_base_url}/index.html" if config.public_base_url else None
    return {
        "connected": True,
        "bucket": config.bucket,
        "viewerUrl": viewer_url,
    }


def upload_file(config: R2Config, source: Path, key: str) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    _client(config).upload_file(
        str(source),
        config.bucket,
        key,
        ExtraArgs={"ContentType": _content_type(source)},
    )


def download_file(config: R2Config, key: str, destination: Path, *, max_bytes: int = 8 * 1024**3) -> None:
    client = _client(config)
    metadata = client.head_object(Bucket=config.bucket, Key=key)
    content_length = int(metadata.get("ContentLength") or 0)
    if content_length < 0 or content_length > max_bytes:
        raise RuntimeError(f"R2上のファイルが許容サイズを超えています: {key}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.download")
    client.download_file(config.bucket, key, str(temporary))
    temporary.replace(destination)


def load_json_object(config: R2Config, key: str) -> dict | list | None:
    try:
        response = _client(config).get_object(Bucket=config.bucket, Key=key)
    except Exception as exc:
        response = getattr(exc, "response", {})
        code = str(response.get("Error", {}).get("Code", ""))
        if code in {"NoSuchKey", "404", "NotFound"}:
            return None
        raise
    body = response["Body"].read(5 * 1024 * 1024 + 1)
    if len(body) > 5 * 1024 * 1024:
        raise RuntimeError(f"R2上の同期情報が許容サイズを超えています: {key}")
    return json.loads(body.decode("utf-8"))


def upload_json_object(config: R2Config, key: str, payload: dict | list) -> None:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    _client(config).put_object(
        Bucket=config.bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )


def upload_session_assets(
    video_id: str,
    *,
    result_file: Path,
    audio_file: Path,
    video_file: Path | None,
    config: R2Config,
) -> None:
    base_key = f"{config.prefix}/{video_id}"
    upload_file(config, result_file, f"{base_key}/session.json")
    upload_file(config, audio_file, f"{base_key}/audio.mp3")
    if video_file is not None and video_file.exists():
        upload_file(config, video_file, f"{base_key}/video.mp4")
    stem_dir = PUBLIC_STEMS_DIR / video_id
    if stem_dir.exists():
        for stem in STEM_NAMES:
            stem_file = stem_dir / f"{stem}.mp3"
            if stem_file.exists():
                upload_file(config, stem_file, f"{base_key}/stems/{stem}.mp3")


def delete_session_assets(video_ids: list[str], config: R2Config) -> None:
    keys = []
    for video_id in video_ids:
        base_key = f"{config.prefix}/{video_id}"
        keys.extend(
            [
                f"{base_key}/session.json",
                f"{base_key}/audio.mp3",
                f"{base_key}/video.mp4",
                *(f"{base_key}/stems/{stem}.mp3" for stem in STEM_NAMES),
            ]
        )
    client = _client(config)
    for start in range(0, len(keys), 1000):
        response = client.delete_objects(
            Bucket=config.bucket,
            Delete={"Objects": [{"Key": key} for key in keys[start:start + 1000]], "Quiet": True},
        )
        errors = response.get("Errors", [])
        if errors:
            messages = ", ".join(f"{item.get('Key')}: {item.get('Message')}" for item in errors[:3])
            raise RuntimeError(f"R2から削除できませんでした: {messages}")


def load_sync_index(config: R2Config) -> dict[str, str] | None:
    key = f"{config.prefix}/sync-index.json"
    try:
        response = _client(config).get_object(Bucket=config.bucket, Key=key)
    except Exception as exc:
        response = getattr(exc, "response", {})
        code = str(response.get("Error", {}).get("Code", ""))
        if code in {"NoSuchKey", "404", "NotFound"}:
            return None
        raise
    body = response["Body"].read(5 * 1024 * 1024 + 1)
    if len(body) > 5 * 1024 * 1024:
        raise RuntimeError("R2上の同期台帳が許容サイズを超えています")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        return None
    files = payload.get("files")
    return files if isinstance(files, dict) else None


def upload_sync_index(config: R2Config, files: dict[str, str]) -> None:
    key = f"{config.prefix}/sync-index.json"
    body = json.dumps({"version": 1, "files": files}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    _client(config).put_object(
        Bucket=config.bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )


def delete_object_keys(config: R2Config, keys: list[str]) -> None:
    client = _client(config)
    for start in range(0, len(keys), 1000):
        batch = keys[start:start + 1000]
        if not batch:
            continue
        response = client.delete_objects(
            Bucket=config.bucket,
            Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
        )
        errors = response.get("Errors", [])
        if errors:
            messages = ", ".join(f"{item.get('Key')}: {item.get('Message')}" for item in errors[:3])
            raise RuntimeError(f"R2から削除できませんでした: {messages}")


def upload_manifest(config: R2Config, manifest_file: Path) -> None:
    upload_file(config, manifest_file, f"{config.prefix}/manifest.json")


def upload_folders(config: R2Config, folders_file: Path) -> None:
    if folders_file.exists():
        upload_file(config, folders_file, f"{config.prefix}/folders.json")


def upload_static_app(config: R2Config, public_dir: Path) -> None:
    for name in ("index.html", "app.js", "styles.css"):
        upload_file(config, public_dir / name, name)


def configure_bucket_cors(config: R2Config, allowed_origins: list[str] | None = None) -> None:
    origins = allowed_origins or ["*"]
    _client(config).put_bucket_cors(
        Bucket=config.bucket,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedOrigins": origins,
                    "AllowedMethods": ["GET", "HEAD"],
                    "AllowedHeaders": ["*"],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 3600,
                }
            ]
        },
    )
