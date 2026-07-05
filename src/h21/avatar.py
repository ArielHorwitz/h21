from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI
from PIL import Image

logger = logging.getLogger("h21.avatar")

THUMBNAIL_SIZE = 128

DEFAULT_PROMPT = (
    "Generate a visually striking profile picture of a random interesting "
    "object or scene. Think: a red telephone on marble, a paper airplane in "
    "sunset sky, a rubber duck on ocean waves, a vintage compass on old maps. "
    "Colorful, bold, memorable at small sizes. Square composition, no text "
    "or letters."
)

REFERENCE_DEFAULT_PROMPT = (
    "Create a stylized profile picture inspired by this image. "
    "Creative interpretation, suitable as a small avatar. "
    "Square composition, no text or letters."
)


def _avatars_dir(data_dir: Path) -> Path:
    avatar_dir = data_dir / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    return avatar_dir


def _original_path(data_dir: Path, player_code: str) -> Path:
    return _avatars_dir(data_dir).joinpath(f"{player_code}_original.png")


def _thumbnail_path(data_dir: Path, player_code: str) -> Path:
    return _avatars_dir(data_dir).joinpath(f"{player_code}.webp")


def _pending_original_path(data_dir: Path, player_code: str) -> Path:
    return _avatars_dir(data_dir).joinpath(f"{player_code}_pending.png")


def _pending_thumbnail_path(data_dir: Path, player_code: str) -> Path:
    return _avatars_dir(data_dir).joinpath(f"{player_code}_pending.webp")


def _create_thumbnail(image_bytes: bytes) -> bytes:
    """Resize an image to THUMBNAIL_SIZE x THUMBNAIL_SIZE and encode as webp."""
    image = Image.open(io.BytesIO(image_bytes))
    image = image.convert("RGB")
    image.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE), Image.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="WEBP", quality=85)
    return output.getvalue()


async def generate_avatar(
    client: AsyncOpenAI,
    model: str,
    *,
    prompt: Optional[str] = None,
    reference_image: Optional[bytes] = None,
) -> bytes:
    """Generate an avatar image via the OpenAI image API.

    Returns the raw PNG bytes of the generated image.

    Uses images.edit() when a reference image is provided (since it accepts
    image input), and images.generate() otherwise.
    """
    effective_prompt = prompt or (
        REFERENCE_DEFAULT_PROMPT if reference_image else DEFAULT_PROMPT
    )

    if reference_image:
        logger.info(
            "Generating avatar with reference image, model=%s, prompt=%r",
            model, effective_prompt[:80],
        )
        # Detect image format from magic bytes for correct MIME type.
        if reference_image[:3] == b"\xff\xd8\xff":
            filename = "reference.jpg"
        elif reference_image[:8] == b"\x89PNG\r\n\x1a\n":
            filename = "reference.png"
        elif reference_image[:4] == b"RIFF" and reference_image[8:12] == b"WEBP":
            filename = "reference.webp"
        else:
            filename = "reference.png"
        result = await client.images.edit(
            model=model,
            image=(filename, io.BytesIO(reference_image)),
            prompt=effective_prompt,
            n=1,
            size="1024x1024",
        )
    else:
        logger.info(
            "Generating avatar without reference, model=%s, prompt=%r",
            model, effective_prompt[:80],
        )
        result = await client.images.generate(
            model=model,
            prompt=effective_prompt,
            n=1,
            size="1024x1024",
        )

    image_b64 = result.data[0].b64_json
    if image_b64 is None:
        raise RuntimeError("Image API did not return base64 data")
    return base64.b64decode(image_b64)


async def generate_auto_avatar(
    client: AsyncOpenAI,
    model: str,
) -> bytes:
    """Generate the automatic default avatar for a new account."""
    return await generate_avatar(client, model)


def save_pending(data_dir: Path, player_code: str, image_bytes: bytes) -> bytes:
    """Save generated image as pending (not yet confirmed).

    Returns the thumbnail bytes for preview.
    """
    pending_original = _pending_original_path(data_dir, player_code)
    pending_original.write_bytes(image_bytes)

    thumbnail_bytes = _create_thumbnail(image_bytes)
    pending_thumbnail = _pending_thumbnail_path(data_dir, player_code)
    pending_thumbnail.write_bytes(thumbnail_bytes)

    return thumbnail_bytes


def confirm_pending(data_dir: Path, player_code: str) -> bool:
    """Move pending avatar files to active. Returns True if pending files existed."""
    pending_original = _pending_original_path(data_dir, player_code)
    pending_thumb = _pending_thumbnail_path(data_dir, player_code)

    if not pending_original.exists():
        return False

    active_original = _original_path(data_dir, player_code)
    active_thumb = _thumbnail_path(data_dir, player_code)

    pending_original.rename(active_original)
    if pending_thumb.exists():
        pending_thumb.rename(active_thumb)

    return True


def save_avatar_direct(data_dir: Path, player_code: str, image_bytes: bytes) -> None:
    """Save an avatar directly (for auto-generation on registration)."""
    original = _original_path(data_dir, player_code)
    original.write_bytes(image_bytes)

    thumbnail_bytes = _create_thumbnail(image_bytes)
    thumbnail = _thumbnail_path(data_dir, player_code)
    thumbnail.write_bytes(thumbnail_bytes)


def discard_pending(data_dir: Path, player_code: str) -> None:
    """Remove pending avatar files if they exist."""
    pending_original = _pending_original_path(data_dir, player_code)
    pending_thumb = _pending_thumbnail_path(data_dir, player_code)
    if pending_original.exists():
        pending_original.unlink()
    if pending_thumb.exists():
        pending_thumb.unlink()


def get_original_path(data_dir: Path, player_code: str) -> Optional[Path]:
    """Return the path to the original avatar if it exists."""
    path = _original_path(data_dir, player_code)
    return path if path.exists() else None


def get_thumbnail_path(data_dir: Path, player_code: str) -> Optional[Path]:
    """Return the path to the thumbnail avatar if it exists."""
    path = _thumbnail_path(data_dir, player_code)
    return path if path.exists() else None


def get_pending_original_path(data_dir: Path, player_code: str) -> Optional[Path]:
    """Return the path to the pending original if it exists."""
    path = _pending_original_path(data_dir, player_code)
    return path if path.exists() else None


def has_avatar(data_dir: Path, player_code: str) -> bool:
    """Check whether an active avatar exists for a player."""
    return _thumbnail_path(data_dir, player_code).exists()
