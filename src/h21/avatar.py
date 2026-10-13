from __future__ import annotations

import base64
import io
import logging
import random
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI
from PIL import Image

logger = logging.getLogger("h21.avatar")

THUMBNAIL_SIZE = 128

# Art styles for generated avatars, each with a few defining words so the
# image model doesn't drift toward its default look. Chosen to stay distinct
# from each other and readable at small sizes.
AVATAR_STYLES = {
    "linocut": "linocut print (bold carved lines, two or three inks)",
    "stained glass": "stained glass (thick dark outlines)",
    "pixel art": "pixel art (chunky 32x32 sprite)",
    "embroidered": "embroidered patch (stitched thread texture)",
    "origami": "origami (folded paper)",
    "mosaic": "mosaic tiles",
    "rubber-hose": "1930s rubber-hose cartoon",
}

# Background colors. Each avatar is offered two and the model picks the one
# that contrasts better with the subject, so backgrounds vary without
# landing a subject on its own color.
AVATAR_BACKGROUNDS = (
    "deep teal", "mustard yellow", "coral pink", "navy blue", "sage green", "terracotta",
    "lavender", "charcoal grey", "sky blue", "forest green", "plum purple", "tomato red",
)

# Low quality is indistinguishable from high at avatar sizes, at a fraction
# of the cost.
AVATAR_QUALITY = "low"

AVATAR_NOUNS = (
    "octopus", "beetle", "chameleon", "peacock", "fox", "owl", "raven",
    "jellyfish", "seahorse", "penguin", "mushroom", "coral", "bonsai",
    "sunflower", "cactus", "maple", "fern", "lotus", "pinecone", "crystal",
    "lantern", "hourglass", "compass", "telescope", "spyglass", "astrolabe",
    "sundial", "key", "locket", "mask", "crown", "helmet", "anchor", "quill",
    "scroll", "book", "pocketwatch", "globe", "dice", "chesspiece", "violin",
    "cello", "harp", "banjo", "saxophone", "trumpet", "tambourine", "ocarina",
    "xylophone", "gramophone", "zeppelin", "canoe", "airship", "submarine",
    "locomotive", "motorcycle", "sailboat", "rocket", "spaceship", "tram",
    "lighthouse", "pagoda", "windmill", "castle", "observatory", "greenhouse",
    "gazebo", "temple", "cathedral", "torii", "pomegranate", "croissant",
    "pineapple", "watermelon", "dragonfruit", "strawberry", "pretzel",
    "cupcake", "donut", "artichoke", "snail", "dragonfly", "butterfly",
    "scorpion", "lobster", "crab", "hedgehog", "koala", "panda", "gecko",
    "volcano", "waterfall", "iceberg", "geyser", "tornado", "moon", "planet",
    "comet", "meteor", "rainbow",
)


def _avatar_prompt_ending(backgrounds: tuple[str, str]) -> str:
    first, second = backgrounds
    return (
        "Distinctive and simple: a single centered subject that reads clearly at small "
        f"sizes, on a plain background in either {first} or {second}, whichever contrasts "
        "better with the subject. Square composition, no border or frame, no text or letters."
    )


def build_avatar_prompt(noun: str, style: str, backgrounds: tuple[str, str]) -> str:
    """Build the generation prompt for a subject, an AVATAR_STYLES key and two backgrounds."""
    return (
        f"A profile picture of a {noun}, in the style of {AVATAR_STYLES[style]}. "
        + _avatar_prompt_ending(backgrounds)
    )


def build_reference_prompt(style: str) -> str:
    """Build the prompt for a picture based on a reference image.

    The background is left to the image, so only the style is imposed.
    """
    return (
        f"A profile picture inspired by this image, in the style of {AVATAR_STYLES[style]}. "
        "Distinctive and simple, reading clearly at small sizes. Square composition, "
        "no border or frame, no text or letters."
    )


def _random_backgrounds() -> tuple[str, str]:
    first, second = random.sample(AVATAR_BACKGROUNDS, 2)
    return first, second


def _random_avatar_prompt() -> str:
    """Build a prompt with a random subject, style and pair of backgrounds."""
    return build_avatar_prompt(
        random.choice(AVATAR_NOUNS), random.choice(list(AVATAR_STYLES)), _random_backgrounds(),
    )


def _random_reference_prompt() -> str:
    return build_reference_prompt(random.choice(list(AVATAR_STYLES)))


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
        _random_reference_prompt() if reference_image else _random_avatar_prompt()
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
            quality=AVATAR_QUALITY,
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
            quality=AVATAR_QUALITY,
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


# Admins start with the H21 admin badge instead of a generated picture.
ADMIN_AVATAR_PATH = Path(__file__).resolve().parents[2].joinpath("static", "brand", "h21-admin-avatar.png")


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


def process_upload(data_dir: Path, player_code: str, image_bytes: bytes) -> None:
    """Process an uploaded image and save as the active avatar.

    Normalizes the image to PNG (original) and creates a webp thumbnail,
    regardless of the input format.
    """
    image = Image.open(io.BytesIO(image_bytes))
    image = image.convert("RGB")

    # Save original as PNG.
    original_buffer = io.BytesIO()
    image.save(original_buffer, format="PNG")
    original_path = _original_path(data_dir, player_code)
    original_path.write_bytes(original_buffer.getvalue())

    # Save thumbnail as webp.
    thumbnail_bytes = _create_thumbnail(image_bytes)
    thumbnail_path = _thumbnail_path(data_dir, player_code)
    thumbnail_path.write_bytes(thumbnail_bytes)


def has_avatar(data_dir: Path, player_code: str) -> bool:
    """Check whether an active avatar exists for a player."""
    return _thumbnail_path(data_dir, player_code).exists()
