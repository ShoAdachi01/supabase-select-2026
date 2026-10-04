"""Copy detection with transparent evidence, not character identity or legal judgments."""

from __future__ import annotations

import base64
import hashlib
import io
import warnings

import numpy as np
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 20_000_000


def image_from_bytes(data: bytes) -> Image.Image:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        image = Image.open(io.BytesIO(data))
        if image.format not in ("PNG", "JPEG", "WEBP", "GIF"):
            raise ValueError("Use a PNG, JPEG, WebP, or GIF image.")
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGBA")
        background = Image.new("RGBA", image.size, "white")
        background.alpha_composite(image)
        return background.convert("RGB")


def png_bytes(image: Image.Image, size: int = 1000) -> bytes:
    image = image.copy()
    image.thumbnail((size, size))
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


def thumbnail(data: bytes) -> str:
    return (
        "data:image/png;base64," + base64.b64encode(png_bytes(image_from_bytes(data), 400)).decode()
    )


def digest(data: bytes) -> str:
    image = image_from_bytes(data)
    return hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()


def perceptual_hash(image: Image.Image) -> np.ndarray:
    values = np.asarray(image.convert("L").resize((32, 32)), dtype=float)
    indices = np.arange(32)
    matrix = np.cos(np.pi * np.outer(np.arange(8), 2 * indices + 1) / 64)
    frequencies = matrix @ values @ matrix.T
    flattened = frequencies.flatten()[1:]
    return flattened > np.median(flattened)


def compare(reference: bytes, candidate: bytes) -> dict:
    if digest(reference) == digest(candidate):
        return {
            "kind": "same_image",
            "distance": 0,
            "reason": "Decoded pixels and dimensions are identical to the reference.",
        }
    ref = image_from_bytes(reference)
    image = image_from_bytes(candidate)
    ref_hash = perceptual_hash(ref)
    variations = [image, ImageOps.mirror(image)]
    width, height = image.size
    # A bounded set of crops helps with artwork embedded inside listing photographs.
    for fraction in (0.8, 0.6):
        for x, y in ((0.5, 0.5), (0, 0), (1, 0), (0, 1), (1, 1)):
            w, h = int(width * fraction), int(height * fraction)
            left, top = int((width - w) * x), int((height - h) * y)
            variations.append(image.crop((left, top, left + w, top + h)))
    distance = min(
        int(np.count_nonzero(ref_hash != perceptual_hash(variant))) for variant in variations
    )
    if distance <= 8:
        kind, reason = (
            "likely_copy",
            "A perceptual fingerprint is close to the reference; inspect the side-by-side images.",
        )
    elif distance <= 16:
        kind, reason = (
            "visually_similar",
            "Some visual structure is similar. This is a candidate, not confirmed character identity.",
        )
    else:
        kind, reason = (
            "unverified",
            "Copy detection did not establish a close match. Different depictions can still contain the character.",
        )
    return {"kind": kind, "distance": distance, "reason": reason}
