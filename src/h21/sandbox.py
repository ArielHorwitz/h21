"""Create and run a seeded local sandbox instance for testing and debugging.

The sandbox lives in its own directory (default: ./.sandbox) holding isolated
XDG config and data directories, so it never touches the real database. It is
seeded with a dev account, friend personas, and fabricated play history so the
app can be experienced as a normal user with active friends. Live play works
normally through the OpenAI API using the real config/key.
"""

from __future__ import annotations

import argparse
import colorsys
import hashlib
import io
import json
import os
import random
import shlex
import shutil
import sqlite3
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw

from h21.avatar import process_upload, save_avatar_direct
from h21.config import _config_dir
from h21.db import GameDatabase, slugify


DEV_USERNAME = "dev"
DEFAULT_SANDBOX_DIR = ".sandbox"
DEFAULT_PASSWORD = "sandbox"
DEFAULT_FRIEND_COUNT = 4
DEFAULT_HISTORY_DAYS = 7
DEFAULT_RNG_SEED = 21

# Account limits for seeded accounts (matches load_config defaults).
DAILY_QUESTION_LIMIT = 200
DAILY_TOPIC_LIMIT = 3
MONTHLY_AVATAR_LIMIT = 3

FRIEND_PERSONAS = [
    ("alice", "Alice"),
    ("bob", "Bob"),
    ("carol", "Carol"),
    ("dana", "Dana"),
    ("eli", "Eli"),
    ("fern", "Fern"),
    ("gil", "Gil"),
    ("hana", "Hana"),
]

# Extra personas that exercise specific features regardless of --friends:
ANONYMOUS_FRIEND = ("zoe", "Zoe")     # mutual friend with the anonymous flag set
FOLLOWER_ONLY = ("felix", "Felix")    # follows dev without a follow-back (suggestion tier 1)
FRIEND_OF_FRIEND = ("gwen", "Gwen")   # followed by the first friend (suggestion tier 2)

# Pre-generated profile pictures, committed to the repo so seeding needs no
# API calls. Regenerate with `h21-sandbox --generate-samples`.
SAMPLE_AVATARS_DIR = Path(__file__).resolve().parents[2].joinpath(
    "assets", "sandbox-avatars",
)
SAMPLE_SIZE = 512

# Each persona's avatar subject, using adjectives/nouns from avatar.py's own
# lists so samples match what live in-game generation produces.
SAMPLE_AVATAR_SUBJECTS: dict[str, tuple[str, str]] = {
    "dev": ("holographic", "octopus"),
    "alice": ("gilded", "fox"),
    "bob": ("cobalt", "owl"),
    "carol": ("blooming", "lotus"),
    "dana": ("crimson", "dragonfly"),
    "eli": ("frosted", "lighthouse"),
    "fern": ("leafy", "fern"),
    "gil": ("copper", "gramophone"),
    "hana": ("coral", "seahorse"),
    "zoe": ("obsidian", "raven"),
    "felix": ("amber", "hedgehog"),
    "gwen": ("iridescent", "butterfly"),
}

EXTRA_TOPICS = ["Movie Classics", "Great Inventions"]

# Fabricated puzzles: topic slug -> list of (solution, five hints).
SOLUTION_POOLS: dict[str, list[tuple[str, list[str]]]] = {
    "notable-people": [
        ("Marie Curie", [
            "This person was born in the 19th century.",
            "This person moved abroad to pursue an education.",
            "This person is closely associated with radioactivity.",
            "This person won Nobel Prizes in two different sciences.",
            "This person shares a name with a chemical element.",
        ]),
        ("Leonardo da Vinci", [
            "This person lived during the Renaissance.",
            "This person was born in Italy.",
            "This person filled notebooks with mirror writing and sketches.",
            "This person designed flying machines centuries before flight.",
            "This person painted the Mona Lisa.",
        ]),
        ("Ada Lovelace", [
            "This person was born in London in the early 19th century.",
            "This person's father was a famous poet.",
            "This person worked on a mechanical calculating engine.",
            "This person is often called the first computer programmer.",
            "A programming language is named after this person.",
        ]),
    ],
    "world-geography": [
        ("Mount Everest", [
            "It sits on a border between two countries.",
            "It is part of a famous mountain range.",
            "It was first summited in 1953.",
            "Climbers need bottled oxygen near its top.",
            "It is the highest point on Earth.",
        ]),
        ("The Amazon River", [
            "It is located in South America.",
            "It flows through a famous rainforest.",
            "It carries more water than any other river.",
            "Pink dolphins live in its waters.",
            "It shares its name with a huge online store.",
        ]),
        ("The Sahara Desert", [
            "It spans several countries.",
            "It is located in Africa.",
            "It is roughly the size of the United States.",
            "Camel caravans have crossed it for centuries.",
            "It is the largest hot desert in the world.",
        ]),
    ],
    "movie-classics": [
        ("Casablanca", [
            "This film was released during World War II.",
            "It is set in a city in Morocco.",
            "Much of it takes place in a nightclub.",
            "It stars Humphrey Bogart and Ingrid Bergman.",
            "'Here's looking at you, kid' comes from this film.",
        ]),
        ("The Godfather", [
            "This film was released in the 1970s.",
            "It is based on a best-selling novel.",
            "It follows a powerful New York family.",
            "Marlon Brando won an Oscar for it.",
            "It opens with a wedding and an offer that can't be refused.",
        ]),
        ("Citizen Kane", [
            "This film was released in 1941.",
            "Its director also stars in the lead role.",
            "It follows the life of a newspaper tycoon.",
            "It is often ranked the greatest film ever made.",
            "Its famous last word is 'Rosebud'.",
        ]),
    ],
    "great-inventions": [
        ("The Printing Press", [
            "It was invented in the 15th century.",
            "It came from Germany.",
            "It uses movable metal type.",
            "Its first famous product was a Bible.",
            "It is credited to Johannes Gutenberg.",
        ]),
        ("The Telescope", [
            "It was invented in the early 17th century.",
            "It first appeared in the Netherlands.",
            "Galileo improved it and turned it toward the sky.",
            "It uses lenses or mirrors.",
            "It lets you see distant objects up close.",
        ]),
        ("The Steam Engine", [
            "It was developed in the 18th century.",
            "It powered the Industrial Revolution.",
            "It converts heat into motion.",
            "James Watt greatly improved it.",
            "It drove early trains and factories.",
        ]),
    ],
}

# Generic questions whose answers hold for every solution in the topic's pool,
# so fabricated transcripts stay consistent no matter which solution is used.
# Answers use the LLM vocabulary: yes, no, partially, depends, win.
QUESTION_POOLS: dict[str, list[tuple[str, str, str]]] = {
    "notable-people": [
        ("Is it a real person?", "yes", "The subject is a real historical figure."),
        ("Is the person alive today?", "no", "The subject died long ago."),
        ("Is the person from Europe?", "yes", "The subject lived and worked in Europe."),
        ("Is the person known for sports?", "no", "The subject is not an athlete."),
        ("Is the person a fictional character?", "no", "The subject really existed."),
        ("Was the person born before the 20th century?", "yes", "The subject was born well before 1900."),
        ("Is the person primarily known as a politician?", "no", "The subject is not known for holding office."),
        ("Is the person known for music?", "no", "The subject is not a musician."),
        ("Is the person widely taught about in schools?", "yes", "The subject appears in most school curricula."),
        ("Is the person considered a genius?", "partially", "Many consider the subject a genius, though the term is subjective."),
        ("Did the person contribute to science or invention?", "yes", "The subject is known for such contributions."),
        ("Was the person wealthy?", "depends", "The subject's fortunes varied over their lifetime."),
    ],
    "world-geography": [
        ("Is it a natural feature?", "yes", "It formed naturally, without human intervention."),
        ("Is it man-made?", "no", "It is entirely natural."),
        ("Is it a city?", "no", "It is not a settlement."),
        ("Is it a country?", "no", "It is a geographic feature, not a nation."),
        ("Is it located in Europe?", "no", "It lies outside Europe."),
        ("Is it famous worldwide?", "yes", "It is known around the globe."),
        ("Does it hold a world record for its size or scale?", "yes", "It is a record-holder among features of its kind."),
        ("Is it underwater?", "no", "It is not submerged."),
        ("Can tourists visit it?", "yes", "It is a well-known travel destination."),
        ("Is it bigger than a city?", "yes", "It covers a vast area."),
        ("Is it cold there?", "depends", "Conditions vary greatly by season and location."),
        ("Is it dangerous to visit?", "partially", "Parts of it can be dangerous without preparation."),
    ],
    "movie-classics": [
        ("Is it a movie?", "yes", "The subject is a film."),
        ("Was it released before 1980?", "yes", "It premiered decades ago."),
        ("Is it animated?", "no", "It is a live-action film."),
        ("Is it in English?", "yes", "It is an English-language film."),
        ("Is it a comedy?", "no", "It is a dramatic film."),
        ("Was it produced in the United States?", "yes", "It is an American production."),
        ("Is it science fiction?", "no", "It is not a science fiction film."),
        ("Was it nominated for Academy Awards?", "yes", "It received Oscar nominations."),
        ("Is it a musical?", "no", "It is not a musical."),
        ("Is it over three hours long?", "no", "Its runtime is under three hours."),
        ("Is it considered one of the greatest films ever made?", "yes", "It regularly appears on greatest-films lists."),
        ("Is it suitable for young children?", "partially", "It is not explicit, but its themes suit older audiences."),
    ],
    "great-inventions": [
        ("Is it an invention?", "yes", "The subject is an invention."),
        ("Is it a person?", "no", "It is a thing, not a person."),
        ("Was it invented in the last 100 years?", "no", "It is far older than a century."),
        ("Is it electronic?", "no", "It predates electronics."),
        ("Is it a physical object?", "yes", "It is a tangible device."),
        ("Is it still used in some form today?", "yes", "Modern descendants of it are still in use."),
        ("Was it invented in Europe?", "yes", "It originated in Europe."),
        ("Is it a weapon?", "no", "It was not designed to harm."),
        ("Did it change the course of history?", "yes", "It had a transformative impact on society."),
        ("Is it powered by electricity?", "no", "The original ran without electricity."),
        ("Is it edible?", "no", "It is not food."),
        ("Could one person carry it?", "depends", "Early versions varied greatly in size."),
    ],
}

# Wrong guesses used as filler questions; none appear in the solution pools.
DECOY_GUESSES: dict[str, list[str]] = {
    "notable-people": [
        "Albert Einstein", "Napoleon Bonaparte", "William Shakespeare",
        "Isaac Newton", "Cleopatra", "Charles Darwin",
        "Galileo Galilei", "Florence Nightingale",
    ],
    "world-geography": [
        "the Nile River", "the Grand Canyon", "Mount Kilimanjaro",
        "the Great Barrier Reef", "the Gobi Desert", "Lake Baikal",
        "the Alps", "Niagara Falls",
    ],
    "movie-classics": [
        "Gone with the Wind", "Psycho", "Singin' in the Rain",
        "12 Angry Men", "Sunset Boulevard", "On the Waterfront",
        "Vertigo", "Some Like It Hot",
    ],
    "great-inventions": [
        "the Wheel", "the Light Bulb", "the Compass", "the Airplane",
        "the Radio", "the Camera", "the Bicycle", "the Sewing Machine",
    ],
}


def _install_avatar(data_dir: Path, player_code: str, username: str) -> None:
    """Give a seeded account a profile picture.

    Uses the pre-generated sample committed to the repo when available
    (an image the in-game generator produced), falling back to a locally
    rendered identicon so seeding never requires API calls.
    """
    sample_path = SAMPLE_AVATARS_DIR.joinpath(f"{username}.webp")
    if sample_path.is_file():
        process_upload(data_dir, player_code, sample_path.read_bytes())
    else:
        save_avatar_direct(data_dir, player_code, _identicon_png(username))


def _generate_samples() -> None:
    """Regenerate the committed sample avatars via the OpenAI image API.

    Mirrors the in-game account-page flow (avatar.generate_avatar with the
    standard prompt template), one image per persona. Requires a real key.
    """
    import asyncio

    from openai import AsyncOpenAI

    from h21.avatar import build_avatar_prompt, generate_avatar
    from h21.config import load_config

    config = load_config()
    client = AsyncOpenAI(api_key=config.openai_api_key)
    SAMPLE_AVATARS_DIR.mkdir(parents=True, exist_ok=True)

    async def generate_one(username: str, adjective: str, noun: str) -> None:
        prompt = build_avatar_prompt(adjective, noun)
        image_bytes = await generate_avatar(
            client, config.avatar_image_model, prompt=prompt,
        )
        sample_path = SAMPLE_AVATARS_DIR.joinpath(f"{username}.webp")
        sample_path.write_bytes(_shrink_sample(image_bytes))
        print(f"  {username}: {adjective} {noun} -> {sample_path.name}")

    async def generate_all() -> None:
        await asyncio.gather(*(
            generate_one(username, adjective, noun)
            for username, (adjective, noun) in SAMPLE_AVATAR_SUBJECTS.items()
        ))

    print(f"Generating {len(SAMPLE_AVATAR_SUBJECTS)} sample avatars "
          f"with {config.avatar_image_model}...")
    asyncio.run(generate_all())
    print(f"Samples written to {SAMPLE_AVATARS_DIR}")


def _shrink_sample(image_bytes: bytes) -> bytes:
    """Downscale a generated image to keep committed samples small."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image.thumbnail((SAMPLE_SIZE, SAMPLE_SIZE), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=85)
    return buffer.getvalue()


def _identicon_png(username: str) -> bytes:
    """Render a deterministic identicon-style avatar for a seeded account.

    Fallback for personas without a committed sample, so seeding works
    offline even when samples are missing.
    """
    digest = hashlib.sha256(username.encode()).digest()
    hue = digest[0] / 255
    foreground = tuple(
        round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, 0.6, 0.8)
    )
    background = tuple(
        round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, 0.15, 0.96)
    )

    cell_size = 48
    margin = cell_size
    image = Image.new("RGB", (cell_size * 5 + margin * 2,) * 2, background)
    draw = ImageDraw.Draw(image)
    # 15 digest bytes fill a 5x5 grid mirrored around the middle column.
    for cell_index, cell_byte in enumerate(digest[1:16]):
        if cell_byte % 2 == 0:
            continue
        row, column = divmod(cell_index, 3)
        for mirrored_column in {column, 4 - column}:
            left = margin + mirrored_column * cell_size
            top = margin + row * cell_size
            draw.rectangle(
                (left, top, left + cell_size - 1, top + cell_size - 1),
                fill=foreground,
            )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@dataclass
class _TimestampFixups:
    """Backdated timestamps to apply after seeding via the regular API."""

    games: list[tuple[str, Optional[str], int]] = field(default_factory=list)
    questions: list[tuple[str, int, int]] = field(default_factory=list)
    hint_reveals: list[tuple[str, int, int]] = field(default_factory=list)
    accounts: list[tuple[str, int]] = field(default_factory=list)


def seed_database(
    db_path: Path,
    *,
    password: str = DEFAULT_PASSWORD,
    friend_count: int = DEFAULT_FRIEND_COUNT,
    history_days: int = DEFAULT_HISTORY_DAYS,
    rng_seed: int = DEFAULT_RNG_SEED,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """Create and populate a sandbox database. Returns a summary dict."""
    if today is None:
        today = date.today()
    friend_count = max(1, min(friend_count, len(FRIEND_PERSONAS)))
    history_days = max(1, history_days)
    rng = random.Random(rng_seed)
    fixups = _TimestampFixups()
    now = datetime.now(timezone.utc)

    database = GameDatabase(db_path)
    database.ensure_schema()

    invite_code = database.create_invite(alias="sandbox", uses=64)

    def create_player(
        username: str, display_name: str,
        role: str = "user", anonymous: bool = False,
    ) -> int:
        database.consume_invite(invite_code)
        user_id = database.create_account(
            username, password, role=role, invite_code=invite_code,
            daily_question_limit=DAILY_QUESTION_LIMIT,
            daily_topic_limit=DAILY_TOPIC_LIMIT,
            monthly_avatar_limit=MONTHLY_AVATAR_LIMIT,
        )
        database.update_profile(user_id, display_name, anonymous)
        player_code = database.get_account_by_id(user_id)["player_code"]
        _install_avatar(db_path.parent, player_code, username)
        database.bump_avatar_version(user_id)
        joined = datetime.combine(
            today - timedelta(days=history_days), datetime.min.time(), timezone.utc,
        ) + timedelta(hours=rng.randint(8, 20), minutes=rng.randint(0, 59))
        fixups.accounts.append((joined.isoformat(), user_id))
        return user_id

    dev_id = create_player(DEV_USERNAME, "Dev", role="dev")
    friend_ids = [
        create_player(username, display_name)
        for username, display_name in FRIEND_PERSONAS[:friend_count]
    ]
    anonymous_id = create_player(*ANONYMOUS_FRIEND, anonymous=True)
    follower_id = create_player(*FOLLOWER_ONLY)
    friend_of_friend_id = create_player(*FRIEND_OF_FRIEND)

    # Mutual friendships between dev and each friend persona (plus the
    # anonymous one), a one-way follower, and a friend-of-friend edge so the
    # friend-suggestion tiers all have candidates.
    for friend_id in [*friend_ids, anonymous_id]:
        database.add_friend(dev_id, friend_id)
        database.add_friend(friend_id, dev_id)
    for first_id, second_id in zip(friend_ids, friend_ids[1:]):
        database.add_friend(first_id, second_id)
        database.add_friend(second_id, first_id)
    database.add_friend(follower_id, dev_id)
    database.add_friend(friend_ids[0], friend_of_friend_id)

    for topic_index, topic_name in enumerate(EXTRA_TOPICS):
        suggester = friend_ids[topic_index % len(friend_ids)]
        database.add_topic(slugify(topic_name), topic_name, user_id=suggester)

    topic_slugs = list(SOLUTION_POOLS)
    difficulties = ("normal", "expert")

    # Fabricated puzzles for every topic/difficulty over the history window.
    puzzle_solutions: dict[tuple[date, str, str], str] = {}
    for day_offset in range(history_days):
        day = today - timedelta(days=day_offset)
        for topic_index, topic_slug in enumerate(topic_slugs):
            pool = SOLUTION_POOLS[topic_slug]
            for difficulty_index, difficulty in enumerate(difficulties):
                solution, hints = pool[
                    (day_offset + topic_index + difficulty_index) % len(pool)
                ]
                database.record_puzzle(day, topic_slug, difficulty, solution, hints=hints)
                puzzle_solutions[(day, topic_slug, difficulty)] = solution

    def seed_game(
        user_id: int, day: date, topic_slug: str, difficulty: str, win: bool,
    ) -> None:
        solution = puzzle_solutions[(day, topic_slug, difficulty)]
        _seed_game(
            database, rng, fixups, now,
            user_id=user_id, day=day, topic_slug=topic_slug,
            difficulty=difficulty, solution=solution, win=win,
        )

    game_count = 0
    for day_offset in range(history_days):
        day = today - timedelta(days=day_offset)
        # One "popular" puzzle per day that most personas play, guaranteeing
        # overlapping results for the friend-activity features.
        popular_slug = topic_slugs[day_offset % len(topic_slugs)]

        for friend_index, friend_id in enumerate(friend_ids):
            if friend_index > 0 and rng.random() > 0.8:
                continue
            # The first friend always plays the popular puzzle and always wins,
            # so shared-win features are guaranteed content.
            win = friend_index == 0 or rng.random() < 0.65
            seed_game(friend_id, day, popular_slug, "normal", win)
            game_count += 1
            if rng.random() < 0.4:
                other_slug = topic_slugs[(day_offset + 1 + friend_index) % len(topic_slugs)]
                seed_game(friend_id, day, other_slug, rng.choice(difficulties), rng.random() < 0.5)
                game_count += 1

        for extra_id in (anonymous_id, follower_id, friend_of_friend_id):
            if rng.random() < 0.5:
                seed_game(extra_id, day, popular_slug, "normal", rng.random() < 0.6)
                game_count += 1

        # Dev has history on past days but nothing today, leaving today's
        # puzzles fresh for live play. Wins on the two most recent past days
        # are forced so recent shared results are guaranteed.
        if day_offset > 0:
            win = day_offset <= 2 or rng.random() < 0.7
            seed_game(dev_id, day, popular_slug, "normal", win)
            game_count += 1
            if rng.random() < 0.5:
                other_slug = topic_slugs[(day_offset + 2) % len(topic_slugs)]
                seed_game(dev_id, day, other_slug, rng.choice(difficulties), rng.random() < 0.6)
                game_count += 1

    database.close()
    _apply_timestamp_fixups(db_path, fixups)

    return {
        "dev_username": DEV_USERNAME,
        "dev_user_id": dev_id,
        "friend_usernames": [username for username, _ in FRIEND_PERSONAS[:friend_count]],
        "anonymous_username": ANONYMOUS_FRIEND[0],
        "follower_username": FOLLOWER_ONLY[0],
        "friend_of_friend_username": FRIEND_OF_FRIEND[0],
        "topic_slugs": topic_slugs,
        "game_count": game_count,
        "puzzle_count": len(puzzle_solutions),
        "history_days": history_days,
        "invite_code": invite_code,
    }


def _seed_game(
    database: GameDatabase,
    rng: random.Random,
    fixups: _TimestampFixups,
    now: datetime,
    *,
    user_id: int,
    day: date,
    topic_slug: str,
    difficulty: str,
    solution: str,
    win: bool,
) -> None:
    """Fabricate one completed game with a plausible transcript."""
    question_pool = QUESTION_POOLS[topic_slug]
    decoys = DECOY_GUESSES[topic_slug]

    transcript = rng.sample(question_pool, rng.randint(5, min(12, len(question_pool))))
    wrong_guesses = [
        (f"Is it {decoy}?", "no", f"It is not {decoy}.")
        for decoy in rng.sample(decoys, rng.randint(1, 3) if win else rng.randint(2, 5))
    ]
    transcript.extend(wrong_guesses)
    rng.shuffle(transcript)
    if win:
        transcript.append((f"Is it {solution}?", "win", f"Correct — it is {solution}!"))

    game = database.create_game(day, topic_slug, difficulty, user_id=user_id)
    game_id = game["game_id"]

    day_start = datetime.combine(day, datetime.min.time(), timezone.utc)
    started_at = day_start + timedelta(
        hours=rng.randint(8, 21), minutes=rng.randint(0, 59), seconds=rng.randint(0, 59),
    )
    # Keep today's fabricated games in the past relative to the actual clock,
    # without slipping onto the previous day.
    started_at = max(day_start, min(started_at, now - timedelta(minutes=rng.randint(45, 240))))

    asked_at = started_at
    for question_number, (question, answer, explanation) in enumerate(transcript, start=1):
        asked_at += timedelta(seconds=rng.randint(25, 120))
        database.record_question(
            game_id, question_number, question, answer, explanation, user_id=user_id,
        )
        fixups.questions.append((asked_at.isoformat(), game_id, question_number))

    if rng.random() < 0.5:
        revealed_at = started_at
        for hint_index in range(rng.randint(1, 3)):
            after_question = min(2 + hint_index * 3, len(transcript))
            revealed_at += timedelta(seconds=rng.randint(60, 300))
            database.record_hint_reveal(game_id, hint_index, after_question)
            fixups.hint_reveals.append((revealed_at.isoformat(), game_id, hint_index))

    database.end_game(game_id, "win" if win else "loss")
    ended_at = asked_at + timedelta(seconds=rng.randint(3, 20))
    fixups.games.append((started_at.isoformat(), ended_at.isoformat(), game_id))


def _apply_timestamp_fixups(db_path: Path, fixups: _TimestampFixups) -> None:
    """Backdate seeded rows; the regular API stamps everything with now()."""
    connection = sqlite3.connect(db_path)
    try:
        connection.executemany(
            "UPDATE games SET started_at = ?, ended_at = ? WHERE game_id = ?",
            fixups.games,
        )
        connection.executemany(
            "UPDATE questions SET asked_at = ? WHERE game_id = ? AND question_number = ?",
            fixups.questions,
        )
        connection.executemany(
            "UPDATE hint_reveals SET revealed_at = ? WHERE game_id = ? AND hint_index = ?",
            fixups.hint_reveals,
        )
        connection.executemany(
            "UPDATE accounts SET created_at = ? WHERE user_id = ?",
            fixups.accounts,
        )
        connection.commit()
    finally:
        connection.close()


def _write_sandbox_config(sandbox_config_path: Path) -> bool:
    """Write the sandbox config.toml, based on the real config when present.

    Returns True if an OpenAI API key made it into the sandbox config.
    """
    source_path = _config_dir() / "config.toml"
    if source_path.is_file():
        raw = tomllib.loads(source_path.read_text())
    else:
        raw = {}
    if not raw.get("openai_api_key") and os.environ.get("OPENAI_API_KEY"):
        raw["openai_api_key"] = os.environ["OPENAI_API_KEY"]
    # Local sandbox runs plain http, and auto avatar generation would burn
    # image-API credits on every fake account.
    raw["secure_cookies"] = False
    raw["auto_generate_missing_avatars"] = False

    lines = []
    for key, value in raw.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key} = {value}")
        else:
            lines.append(f"{key} = {json.dumps(str(value))}")
    sandbox_config_path.write_text("\n".join(lines) + "\n")
    return bool(raw.get("openai_api_key"))


def _sandbox_env(sandbox_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(sandbox_dir / "config")
    env["XDG_DATA_HOME"] = str(sandbox_dir / "data")
    return env


def _serve(sandbox_dir: Path, port: int) -> None:
    server_binary = shutil.which("h21")
    if server_binary is None:
        print("Could not find the 'h21' command on PATH.", file=sys.stderr)
        print("Run from the project environment (e.g. 'uv run h21-sandbox --serve').", file=sys.stderr)
        sys.exit(1)
    os.execvpe(server_binary, ["h21", "--port", str(port)], _sandbox_env(sandbox_dir))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create and run a seeded local sandbox instance",
    )
    parser.add_argument(
        "--dir", default=DEFAULT_SANDBOX_DIR,
        help=f"Sandbox directory (default: {DEFAULT_SANDBOX_DIR})",
    )
    parser.add_argument(
        "--password", default=DEFAULT_PASSWORD,
        help=f"Password for all seeded accounts (default: {DEFAULT_PASSWORD})",
    )
    parser.add_argument(
        "--friends", type=int, default=DEFAULT_FRIEND_COUNT,
        help=f"Number of mutual-friend personas, up to {len(FRIEND_PERSONAS)} "
             f"(default: {DEFAULT_FRIEND_COUNT})",
    )
    parser.add_argument(
        "--days", type=int, default=DEFAULT_HISTORY_DAYS,
        help=f"Days of play history including today (default: {DEFAULT_HISTORY_DAYS})",
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_RNG_SEED,
        help=f"Random seed for reproducible data (default: {DEFAULT_RNG_SEED})",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Delete and recreate an existing sandbox",
    )
    parser.add_argument(
        "--serve", action="store_true",
        help="Start the server on the sandbox after creating (or reusing) it",
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Port for --serve (default: 8000)",
    )
    parser.add_argument(
        "--generate-samples", action="store_true",
        help="Regenerate the committed sample avatars via the image API, then exit",
    )
    args = parser.parse_args()

    if args.generate_samples:
        _generate_samples()
        return

    sandbox_dir = Path(args.dir).resolve()
    db_path = sandbox_dir.joinpath("data", "h21", "h21.db")

    if db_path.is_file() and not args.force:
        if not args.serve:
            print(f"Sandbox already exists at {sandbox_dir}.")
            print("Use --serve to run it, or --force to recreate it.")
            sys.exit(1)
        print(f"Reusing existing sandbox at {sandbox_dir}.")
    else:
        if sandbox_dir.exists() and args.force:
            shutil.rmtree(sandbox_dir)
        sandbox_dir.joinpath("config", "h21").mkdir(parents=True, exist_ok=True)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        has_api_key = _write_sandbox_config(
            sandbox_dir.joinpath("config", "h21", "config.toml"),
        )
        summary = seed_database(
            db_path,
            password=args.password,
            friend_count=args.friends,
            history_days=args.days,
            rng_seed=args.seed,
        )
        _print_summary(sandbox_dir, args.password, args.port, summary, has_api_key)

    if args.serve:
        _serve(sandbox_dir, args.port)


def _print_summary(
    sandbox_dir: Path, password: str, port: int,
    summary: dict[str, Any], has_api_key: bool,
) -> None:
    friends = ", ".join(summary["friend_usernames"])
    print(f"Sandbox created at {sandbox_dir}")
    print(f"Seeded {summary['game_count']} games and {summary['puzzle_count']} puzzles "
          f"over {summary['history_days']} days.")
    print()
    print(f"Accounts (password for all: {password!r}):")
    print(f"  {summary['dev_username']:12s} your account (role: dev)")
    print(f"  {friends:12s} mutual friends with play history")
    print(f"  {summary['anonymous_username']:12s} mutual friend who plays anonymously")
    print(f"  {summary['follower_username']:12s} follows you (friend suggestion, tier 1)")
    print(f"  {summary['friend_of_friend_username']:12s} friend of a friend (friend suggestion, tier 2)")
    print()
    if not has_api_key:
        print("WARNING: no OpenAI API key found in the real config or environment.")
        print("Set OPENAI_API_KEY to start the server and play live games.")
        print()
    print("Run the sandbox server with:")
    print(f"  h21-sandbox --dir {shlex.quote(str(sandbox_dir))} --serve --port {port}")
    print("or:")
    print(f"  XDG_CONFIG_HOME={shlex.quote(str(sandbox_dir / 'config'))} "
          f"XDG_DATA_HOME={shlex.quote(str(sandbox_dir / 'data'))} h21 --port {port}")
