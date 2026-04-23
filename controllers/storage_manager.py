import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

try:
    import boto3
    from botocore.config import Config as BotoConfig

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


APP_PREFIX = "niassaavanca"
AVATARS_FOLDER = f"{APP_PREFIX}/avatars"
POSTS_FOLDER = f"{APP_PREFIX}/posts"
COMPANIES_FOLDER = f"{APP_PREFIX}/companies"

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "bluesparkmz")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://storage.bluesparkmz.com")
R2_ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else None

R2_CONFIGURED = all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME])


def _guess_extension(upload: UploadFile) -> str:
    filename_ext = Path(upload.filename).suffix.lower().lstrip(".") if upload.filename else ""
    if filename_ext:
        return filename_ext
    ct = (upload.content_type or "").lower()
    ct_map = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/ogg": "ogg",
        "audio/webm": "webm",
        "audio/mp4": "m4a",
    }
    return ct_map.get(ct, "")


class StorageManager:
    def __init__(self) -> None:
        self.use_r2 = R2_CONFIGURED and BOTO3_AVAILABLE
        self.bucket_name = R2_BUCKET_NAME
        self.public_url = R2_PUBLIC_URL.rstrip("/")
        self.s3_client = None

        if self.use_r2:
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=R2_ENDPOINT_URL,
                aws_access_key_id=R2_ACCESS_KEY_ID,
                aws_secret_access_key=R2_SECRET_ACCESS_KEY,
                config=BotoConfig(signature_version="s3v4"),
                region_name="auto",
            )

    def _require_config(self) -> None:
        if self.use_r2:
            return
        detail = "Cloudflare R2 nao configurado."
        if not BOTO3_AVAILABLE:
            detail = "Dependencia boto3 ausente."
        raise HTTPException(status_code=500, detail=detail)

    async def upload_file(
        self,
        file: UploadFile,
        folder: str,
        *,
        allowed_mime_prefixes: tuple[str, ...],
        custom_filename: str | None = None,
    ) -> str:
        self._require_config()

        content_type = file.content_type or ""
        if allowed_mime_prefixes and not any(content_type.startswith(prefix) for prefix in allowed_mime_prefixes):
            raise HTTPException(status_code=400, detail="Tipo de arquivo nao permitido")

        ext = _guess_extension(file)
        if custom_filename:
            filename = custom_filename
        else:
            filename = f"{uuid.uuid4().hex}{('.' + ext) if ext else ''}"

        clean_folder = folder.strip("/")
        key = f"{clean_folder}/{filename}" if clean_folder else filename
        body = await file.read()

        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=body,
            ContentType=content_type or "application/octet-stream",
        )
        return f"{self.public_url}/{key}"


storage_manager = StorageManager()
