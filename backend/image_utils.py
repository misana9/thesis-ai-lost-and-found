from io import BytesIO

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB
MAX_IMAGE_EDGE = 1024


async def read_and_sanitize_image(upload: UploadFile) -> tuple[Image.Image, bytes]:
    if not upload.content_type or not upload.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="A valid image file is required")

    raw = await upload.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty image upload")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image must be 8 MB or smaller")

    try:
        image = Image.open(BytesIO(raw))
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not process the uploaded image") from exc

    image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)

    out = BytesIO()
    image.save(out, format="JPEG", quality=90, optimize=True)
    return image, out.getvalue()
