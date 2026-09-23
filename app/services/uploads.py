"""Зураг хүлээн авах: өргөтгөл, хэмжээ, агуулгыг шалгаж, JPEG болгон дахин кодлоно (EXIF/хортой агуулга арилна)."""
import io
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "MPO"}
Image.MAX_IMAGE_PIXELS = 40_000_000  # "decompression bomb"-оос хамгаална


class UploadError(Exception):
    pass


def has_file(upload: UploadFile | None) -> bool:
    return upload is not None and bool(upload.filename)


def save_image(upload: UploadFile | None, folder: str, max_side: int = 1600) -> str | None:
    """Амжилттай бол static хавтастай харьцангуй замыг ("uploads/issues/x.jpg") буцаана."""
    if not has_file(upload):
        return None
    ext = Path(upload.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise UploadError("Зөвхөн JPG, PNG, WEBP, GIF форматтай зураг оруулна уу.")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = upload.file.read(max_bytes + 1)
    if not data:
        raise UploadError("Зургийн файл хоосон байна.")
    if len(data) > max_bytes:
        raise UploadError(f"Зургийн хэмжээ {settings.max_upload_mb}MB-аас ихгүй байх ёстой.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise UploadError("Зургийн формат дэмжигдэхгүй байна.")
            probe.verify()
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side))
            name = f"{uuid.uuid4().hex}.jpg"
            dest_dir = settings.upload_dir / folder
            dest_dir.mkdir(parents=True, exist_ok=True)
            im.save(dest_dir / name, "JPEG", quality=85, optimize=True)
    except UploadError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise UploadError("Зургийн файл гэмтэлтэй эсвэл зураг биш байна.")
    return f"uploads/{folder}/{name}"


def delete_image(rel_path: str | None) -> None:
    """Зөвхөн uploads хавтас доторх файлыг устгана."""
    if not rel_path:
        return
    try:
        target = (settings.static_dir / rel_path).resolve()
        if settings.upload_dir.resolve() in target.parents and target.is_file():
            target.unlink()
    except OSError:
        pass
