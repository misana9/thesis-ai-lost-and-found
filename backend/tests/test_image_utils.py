import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from image_utils import read_and_sanitize_image


def upload_for_image(size: tuple[int, int]) -> UploadFile:
    buffer = BytesIO()
    Image.new("RGB", size).save(buffer, format="PNG")
    buffer.seek(0)
    return UploadFile(file=buffer, filename="test.png", headers={"content-type": "image/png"})


def test_rejects_image_over_edge_limit():
    with pytest.raises(HTTPException, match="dimensions are too large"):
        asyncio.run(read_and_sanitize_image(upload_for_image((8193, 1))))


def test_rejects_image_over_pixel_limit():
    with pytest.raises(HTTPException, match="dimensions are too large"):
        asyncio.run(read_and_sanitize_image(upload_for_image((5000, 4001))))


def test_sanitizes_image_within_limits():
    image, jpeg_bytes = asyncio.run(read_and_sanitize_image(upload_for_image((100, 80))))

    assert image.size == (100, 80)
    assert jpeg_bytes[:2] == b"\xff\xd8"