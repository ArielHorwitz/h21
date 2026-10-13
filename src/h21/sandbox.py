"""Create and run a seeded local sandbox instance for testing and debugging.

The sandbox lives in its own directory (default: ./.sandbox) holding isolated
XDG config and data directories, so it never touches the real database. It is
seeded with an admin account, friend personas, and fabricated play history so the
app can be experienced as a normal user with active friends. Puzzles are drawn
from committed, pre-generated pools; live play (answering questions, hints)
works through the OpenAI API using the real config/key.
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
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from h21.avatar import ADMIN_AVATAR_PATH, process_upload, save_avatar_direct
from h21.config import _config_dir
from h21.db import GameDatabase, slugify


ADMIN_USERNAME = "admin"
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
FOLLOWER_ONLY = ("felix", "Felix")    # follows admin without a follow-back (suggestion tier 1)
FRIEND_OF_FRIEND = ("gwen", "Gwen")   # followed by the first friend (suggestion tier 2)

# Pre-generated profile pictures, committed to the repo so seeding needs no
# API calls. Regenerate with `h21-sandbox --generate-samples`.
SAMPLE_AVATARS_DIR = Path(__file__).resolve().parents[2].joinpath(
    "assets", "sandbox-avatars",
)
SAMPLE_SIZE = 512

# Each persona's avatar solution as (style, noun), using avatar.py's own styles
# and nouns so samples match what live in-game generation produces.
SAMPLE_AVATAR_SUBJECTS: dict[str, tuple[str, str]] = {
    "alice": ("linocut", "fox"),
    "bob": ("mosaic", "owl"),
    "carol": ("embroidered", "lotus"),
    "dana": ("origami", "dragonfly"),
    "eli": ("pixel art", "lighthouse"),
    "fern": ("embroidered", "fern"),
    "gil": ("rubber-hose", "gramophone"),
    "hana": ("stained glass", "seahorse"),
    "zoe": ("linocut", "raven"),
    "felix": ("pixel art", "hedgehog"),
    "gwen": ("mosaic", "butterfly"),
}

# Players outside admin's circle: they fill global leaderboards beyond friends.
# One has a very long display name, one has no picture, one is blocked.
STRANGER_PERSONAS = [
    ("sam", "Sam"), ("priya", "Priya"), ("lena", "Lena"), ("kofi", "Kofi"),
    ("bartholomew", "Bartholomew Fitzgerald-Montgomery III"),
]
NO_PICTURE_PERSONA = ("omar", "Omar")
BLOCKED_PERSONA = ("troll", "Troll")

# Topics turned down for different players and reasons, as (slug, name,
# suggester index into the friends, detail); index None means admin.
TURNED_DOWN_TOPICS = [
    ("left-handed-accordion-makers", "Left-Handed Accordion Makers", None,
     "We could only make 4 expert and 11 normal solutions; each difficulty needs at least 50."),
    ("medieval-belgian-tax-law", "Medieval Belgian Tax Law", 0,
     "We could only make 2 expert and 9 normal solutions; each difficulty needs at least 50."),
    ("my-cats-favorite-toys", "My Cat's Favorite Toys", 1,
     "We could only make 0 expert and 0 normal solutions; each difficulty needs at least 50."),
    ("ancient-roman-pottery", "Ancient Roman Pottery", 2,
     "Something went wrong while creating puzzles. Try again later."),
]
# A topic of admin's left mid-build: the server builds it for real on startup.
BUILDING_TOPIC = ("jazz-musicians", "Jazz Musicians")

EXTRA_TOPICS = ["Movie Classics", "Great Inventions"]

# Pre-generated puzzle pools for the sandbox topics (topic slug -> difficulty
# -> solutions), produced once by the real generation and validation pipeline
# and committed, so playing in the sandbox draws puzzles without API calls.
SAMPLE_POOLS_PATH = Path(__file__).resolve().parents[2].joinpath(
    "assets", "sandbox-pools.json",
)
SANDBOX_TOPIC_NAMES = {
    "notable-people": "Notable People",
    "world-geography": "World Geography",
    **{slugify(name): name for name in EXTRA_TOPICS},
}

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
        ("Is it a real person?", "yes", "The solution is a real historical figure."),
        ("Is the person alive today?", "no", "The solution died long ago."),
        ("Is the person from Europe?", "yes", "The solution lived and worked in Europe."),
        ("Is the person known for sports?", "no", "The solution is not an athlete."),
        ("Is the person a fictional character?", "no", "The solution really existed."),
        ("Was the person born before the 20th century?", "yes", "The solution was born well before 1900."),
        ("Is the person primarily known as a politician?", "no", "The solution is not known for holding office."),
        ("Is the person known for music?", "no", "The solution is not a musician."),
        ("Is the person widely taught about in schools?", "yes", "The solution appears in most school curricula."),
        ("Is the person considered a genius?", "partially", "Many consider the solution a genius, though the term is subjective."),
        ("Did the person contribute to science or invention?", "yes", "The solution is known for such contributions."),
        ("Was the person wealthy?", "depends", "The solution's fortunes varied over their lifetime."),
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
        ("Is it a movie?", "yes", "The solution is a film."),
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
        ("Is it an invention?", "yes", "The solution is an invention."),
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
# Questions for topics without hand-written ones. Answers are fabricated,
# so they only need to read plausibly in a transcript.
GENERIC_QUESTIONS: list[tuple[str, str, str]] = [
    ("Is it a person?", "no", "The solution is not a person."),
    ("Is it well known?", "yes", "Most people would recognize the solution."),
    ("Is it older than a hundred years?", "partially", "Parts of its story go back that far."),
    ("Is it associated with Europe?", "depends", "That depends on which aspect you mean."),
    ("Is it something you can touch?", "yes", "The solution is physical."),
    ("Is it bigger than a car?", "no", "The solution is smaller than a car."),
    ("Is it still around today?", "yes", "The solution still exists."),
    ("Is it connected to entertainment?", "partially", "It has some ties to entertainment."),
    ("Is it from the 20th century?", "no", "It is not from the 20th century."),
    ("Is it used every day?", "depends", "That depends on who you ask."),
    ("Is it famous worldwide?", "yes", "It is known around the world."),
    ("Is it natural rather than man-made?", "no", "It was made by people."),
]

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

    from h21.avatar import AVATAR_BACKGROUNDS, build_avatar_prompt, generate_avatar
    from h21.config import load_config

    config = load_config()
    client = AsyncOpenAI(api_key=config.openai_api_key)
    SAMPLE_AVATARS_DIR.mkdir(parents=True, exist_ok=True)

    async def generate_one(username: str, style: str, noun: str) -> None:
        first, second = random.sample(AVATAR_BACKGROUNDS, 2)
        prompt = build_avatar_prompt(noun, style, (first, second))
        image_bytes = await generate_avatar(
            client, config.avatar_image_model, prompt=prompt,
        )
        sample_path = SAMPLE_AVATARS_DIR.joinpath(f"{username}.webp")
        sample_path.write_bytes(_shrink_sample(image_bytes))
        print(f"  {username}: {style} {noun} -> {sample_path.name}")

    async def generate_all() -> None:
        await asyncio.gather(*(
            generate_one(username, style, noun)
            for username, (style, noun) in SAMPLE_AVATAR_SUBJECTS.items()
        ))

    print(f"Generating {len(SAMPLE_AVATAR_SUBJECTS)} sample avatars "
          f"with {config.avatar_image_model}...")
    asyncio.run(generate_all())
    print(f"Samples written to {SAMPLE_AVATARS_DIR}")


def _generate_pools() -> None:
    """Regenerate the committed sandbox puzzle pools via the real pipeline.

    One generation batch and one validation call per topic and difficulty,
    as when a topic is created in the app. Requires a real key.
    """
    import asyncio

    from h21.config import load_config
    from h21.db import VALID_DIFFICULTIES
    from h21.llm import OpenAIClient, generate_solution_batch, validate_solution_batch

    config = load_config()
    client = OpenAIClient(
        config.openai_api_key, model=config.model, reasoning_effort=config.reasoning_effort,
    )

    async def generate_one(topic_slug: str, difficulty: str) -> list[str]:
        topic_name = SANDBOX_TOPIC_NAMES[topic_slug]
        exclusion_list = [solution for solution, _ in SOLUTION_POOLS.get(topic_slug, [])]
        batch = await generate_solution_batch(
            client, exclusion_list, topic_name, difficulty, batch_size=100,
        )
        validation = await validate_solution_batch(
            client, batch.solutions, exclusion_list, topic_name, difficulty,
        )
        kept = [result.solution for result in validation.results if result.kept]
        print(f"  {topic_slug} {difficulty}: kept {len(kept)} of {len(batch.solutions)}")
        return kept

    async def generate_all() -> dict[str, dict[str, list[str]]]:
        keys = [
            (topic_slug, difficulty)
            for topic_slug in SANDBOX_TOPIC_NAMES
            for difficulty in sorted(VALID_DIFFICULTIES)
        ]
        results = await asyncio.gather(*(generate_one(*key) for key in keys))
        pools: dict[str, dict[str, list[str]]] = {}
        for (topic_slug, difficulty), solutions in zip(keys, results):
            pools.setdefault(topic_slug, {})[difficulty] = solutions
        return pools

    print(f"Generating sandbox puzzle pools with {config.model}...")
    pools = asyncio.run(generate_all())
    SAMPLE_POOLS_PATH.write_text(json.dumps(pools, indent=2, ensure_ascii=False) + "\n")
    print(f"Pools written to {SAMPLE_POOLS_PATH}")


def _seed_pools(database: GameDatabase) -> int:
    """Fill the sandbox topics' puzzle pools from the committed sample pools.

    Solutions already used as fabricated puzzles, or already pooled at the
    other difficulty, are skipped. Returns the number of solutions pooled.
    """
    if not SAMPLE_POOLS_PATH.is_file():
        return 0
    pools = json.loads(SAMPLE_POOLS_PATH.read_text())
    pooled = 0
    for topic_slug, solutions_by_difficulty in pools.items():
        if database.get_topic(topic_slug) is None:
            continue
        for difficulty, solutions in solutions_by_difficulty.items():
            known = set(database.get_all_known_solutions(topic_slug))
            fresh_solutions = [solution for solution in solutions if solution not in known]
            pooled += database.insert_pool_solutions(topic_slug, difficulty, fresh_solutions)
    return pooled


def _seed_series(database: GameDatabase, rng: random.Random, skip: frozenset[str] = frozenset()) -> None:
    """Give each ready topic its series and preview, as a topic build would.

    Topics in `skip` (ones that existed before seeding) are left alone.

    A series is available if its pool meets the same minimum as a real build,
    and unavailable otherwise. The preview is a random sample here, where a
    real build has a model choose it.
    """
    from h21.main import PREVIEW_SIZE, SERIES_MIN_SOLUTIONS

    for topic in database.get_topics_with_status("ready"):
        if topic["slug"] in skip:
            continue
        available = []
        for difficulty in ("normal", "expert"):
            enough = database.pool_count(topic["slug"], difficulty) >= SERIES_MIN_SOLUTIONS
            database.set_series_status(topic["slug"], difficulty, "available" if enough else "unavailable")
            if enough:
                available.append(difficulty)
        if available:
            candidates = database.get_pool_solutions(topic["slug"], available[0])
            database.set_preview_solutions(topic["slug"], rng.sample(candidates, PREVIEW_SIZE))


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
    topics: list[tuple[str, str]] = field(default_factory=list)


def seed_database(
    db_path: Path,
    *,
    password: str = DEFAULT_PASSWORD,
    friend_count: int = DEFAULT_FRIEND_COUNT,
    history_days: int = DEFAULT_HISTORY_DAYS,
    rng_seed: int = DEFAULT_RNG_SEED,
    today: Optional[date] = None,
    time_zone: Optional[str] = None,
) -> dict[str, Any]:
    """Create and populate a sandbox database. Returns a summary dict.

    "Today" is the date in `time_zone` (admin's, since each player's day
    follows their own clock), or the system's local date.

    An existing database is added to rather than replaced: an existing
    account with a persona's name is reused as is, and topics that already
    exist keep their series, previews and dates.
    """
    if today is None:
        today = _today_in(time_zone)
    friend_count = max(1, min(friend_count, len(FRIEND_PERSONAS)))
    history_days = max(1, history_days)
    rng = random.Random(rng_seed)
    fixups = _TimestampFixups()
    now = datetime.now(timezone.utc)

    database = GameDatabase(db_path)
    database.ensure_schema()
    existing_topics = frozenset(topic["slug"] for topic in database.get_all_topics())
    # The base topics are created ready, like an admin's first suggestions;
    # their pools come from the committed sample pools below.
    for topic_slug in ("notable-people", "world-geography"):
        database.add_topic(topic_slug, SANDBOX_TOPIC_NAMES[topic_slug], status="ready")

    invite_code = database.create_invite(alias="sandbox", uses=64)

    def create_player(
        username: str, display_name: str,
        role: str = "user", anonymous: bool = False, with_picture: bool = True,
    ) -> int:
        existing = database.get_account_by_username(username)
        if existing is not None:
            return existing["user_id"]
        database.consume_invite(invite_code)
        user_id = database.create_account(
            username, password, role=role, invite_code=invite_code,
            daily_question_limit=DAILY_QUESTION_LIMIT,
            daily_topic_limit=DAILY_TOPIC_LIMIT,
            monthly_avatar_limit=MONTHLY_AVATAR_LIMIT,
        )
        database.update_profile(user_id, display_name, anonymous)
        player_code = database.get_account_by_id(user_id)["player_code"]
        if role == "admin":
            save_avatar_direct(db_path.parent, player_code, ADMIN_AVATAR_PATH.read_bytes())
            database.bump_avatar_version(user_id)
        elif with_picture:
            _install_avatar(db_path.parent, player_code, username)
            database.bump_avatar_version(user_id)
        joined = datetime.combine(
            today - timedelta(days=history_days), datetime.min.time(), timezone.utc,
        ) + timedelta(hours=rng.randint(8, 20), minutes=rng.randint(0, 59))
        fixups.accounts.append((joined.isoformat(), user_id))
        return user_id

    admin_id = create_player(ADMIN_USERNAME, "Admin", role="admin")
    if time_zone:
        database.set_time_zone(admin_id, time_zone)
    friend_ids = [
        create_player(username, display_name)
        for username, display_name in FRIEND_PERSONAS[:friend_count]
    ]
    anonymous_id = create_player(*ANONYMOUS_FRIEND, anonymous=True)
    follower_id = create_player(*FOLLOWER_ONLY)
    friend_of_friend_id = create_player(*FRIEND_OF_FRIEND)

    # Mutual friendships between admin and each friend persona (plus the
    # anonymous one), a one-way follower, and a friend-of-friend edge so the
    # friend-suggestion tiers all have candidates.
    for friend_id in [*friend_ids, anonymous_id]:
        database.add_friend(admin_id, friend_id)
        database.add_friend(friend_id, admin_id)
    for first_id, second_id in zip(friend_ids, friend_ids[1:]):
        database.add_friend(first_id, second_id)
        database.add_friend(second_id, first_id)
    database.add_friend(follower_id, admin_id)
    database.add_friend(friend_ids[0], friend_of_friend_id)

    for topic_index, topic_name in enumerate(EXTRA_TOPICS):
        suggester = friend_ids[topic_index % len(friend_ids)]
        database.add_topic(
            slugify(topic_name), topic_name, user_id=suggester, status="ready",
        )

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
        finished: bool = True, question_count: Optional[int] = None,
        hint_count: Optional[int] = None,
    ) -> None:
        solution = puzzle_solutions[(day, topic_slug, difficulty)]
        _seed_game(
            database, rng, fixups, now,
            user_id=user_id, day=day, topic_slug=topic_slug,
            difficulty=difficulty, solution=solution, win=win,
            finished=finished, question_count=question_count, hint_count=hint_count,
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

        # Admin has history on past days; today is covered separately below.
        # Wins on the two most recent past days are forced so recent shared
        # results are guaranteed.
        if day_offset > 0:
            win = day_offset <= 2 or rng.random() < 0.7
            seed_game(admin_id, day, popular_slug, "normal", win)
            game_count += 1
            if rng.random() < 0.5:
                other_slug = topic_slugs[(day_offset + 2) % len(topic_slugs)]
                seed_game(admin_id, day, other_slug, rng.choice(difficulties), rng.random() < 0.6)
                game_count += 1

    # Today, admin has one puzzle in each state (solved, not solved, in
    # progress) and the rest unplayed for live play. A friend is mid-game
    # too, and a game from earlier in the week shows how abandoned games
    # (a rare state set by the system or an admin) look in history.
    def seed_unplayed(user_id: int, day: date, topic_slug: str, difficulty: str, **options: Any) -> int:
        """Seed a game unless the user already played that puzzle. Returns games added."""
        if database.get_existing_game(user_id, day, topic_slug, difficulty) is not None:
            return 0
        seed_game(user_id, day, topic_slug, difficulty, **options)
        return 1

    game_count += seed_unplayed(admin_id, today, topic_slugs[1], "normal", win=True)
    game_count += seed_unplayed(admin_id, today, topic_slugs[0], "expert", win=False)
    game_count += seed_unplayed(
        admin_id, today, topic_slugs[0], "normal", win=False, finished=False, question_count=6,
        hint_count=1,
    )
    game_count += seed_unplayed(
        friend_ids[0], today, topic_slugs[1], "expert", win=False, finished=False, question_count=4,
    )
    # Friends who didn't solve a puzzle admin solved, today and yesterday, to
    # check that unsolved games stay out of every social view.
    def seed_friend_loss(day: date, topic_slug: str, difficulty: str) -> int:
        for friend_id in friend_ids[1:]:
            added = seed_unplayed(friend_id, day, topic_slug, difficulty, win=False)
            if added:
                return added
        return 0

    game_count += seed_friend_loss(today, topic_slugs[1], "normal")
    if history_days > 1:
        game_count += seed_friend_loss(today - timedelta(days=1), topic_slugs[1 % len(topic_slugs)], "normal")

    if history_days > 3:
        abandoned_day = today - timedelta(days=3)
        abandoned_slug = topic_slugs[3 % len(topic_slugs)]
        added = seed_unplayed(admin_id, abandoned_day, abandoned_slug, "expert", win=False, finished=False)
        if added:
            abandoned = database.get_existing_game(admin_id, abandoned_day, abandoned_slug, "expert")
            database.end_game(abandoned["game_id"], "abandoned")
        game_count += added

    # -- Edge cases: everything else the app can show --

    # Admin's history covers every way a game can end.
    def seed_admin_special(**options: Any) -> int:
        """Seed a game for admin on the most recent past day with an unplayed puzzle."""
        for day_offset in range(1, history_days):
            day = today - timedelta(days=day_offset)
            for topic_slug in topic_slugs:
                for difficulty in difficulties:
                    if (day, topic_slug, difficulty) in puzzle_solutions and \
                            database.get_existing_game(admin_id, day, topic_slug, difficulty) is None:
                        seed_game(admin_id, day, topic_slug, difficulty, **options)
                        return 1
        return 0

    game_count += seed_admin_special(win=True, question_count=1, hint_count=0)
    game_count += seed_admin_special(win=True, question_count=20, hint_count=5)
    game_count += seed_admin_special(win=False, question_count=21, hint_count=2)
    game_count += seed_admin_special(win=False, question_count=3, hint_count=0)

    # A game from yesterday still in progress carries over: its series
    # offers it until it ends, with today's puzzle waiting behind it.
    def seed_carried_over() -> int:
        yesterday = today - timedelta(days=1)
        for topic_slug in topic_slugs:
            for difficulty in difficulties:
                if (yesterday, topic_slug, difficulty) in puzzle_solutions \
                        and database.get_existing_game(admin_id, yesterday, topic_slug, difficulty) is None \
                        and database.get_existing_game(admin_id, today, topic_slug, difficulty) is None:
                    seed_game(admin_id, yesterday, topic_slug, difficulty, win=False, finished=False, question_count=5)
                    return 1
        return 0

    if history_days > 1:
        game_count += seed_carried_over()

    # Strangers play today's popular puzzles, mostly solving them.
    stranger_ids = [create_player(username, display_name) for username, display_name in STRANGER_PERSONAS]
    stranger_ids.append(create_player(*NO_PICTURE_PERSONA, with_picture=False))
    blocked_id = create_player(*BLOCKED_PERSONA)
    database.set_account_blocked(blocked_id, True)
    for stranger_id in stranger_ids:
        for topic_slug in topic_slugs[:2]:
            for difficulty in difficulties:
                if rng.random() < 0.6:
                    game_count += seed_unplayed(
                        stranger_id, today, topic_slug, difficulty, win=rng.random() < 0.75,
                    )

    # Topics turned down for several players, and one of admin's still building.
    for slug, name, suggester_index, detail in TURNED_DOWN_TOPICS:
        suggester = admin_id if suggester_index is None else friend_ids[suggester_index % len(friend_ids)]
        database.add_topic(slug, name, user_id=suggester, status="failed")
        database.set_topic_status(slug, "failed", detail)
    database.add_topic(*BUILDING_TOPIC, user_id=admin_id, status="generating")
    # The newest extra topic is admin's own, so "Your topics" has a ready one.
    database.set_topic_owner(slugify(EXTRA_TOPICS[-1]), admin_id)

    # Usage: admin has used a suggestion today; one friend has used up both
    # topic suggestions and picture generations, so their limits show.
    database.increment_daily_topic_suggestions(admin_id, today)
    exhausted_id = friend_ids[1 % len(friend_ids)]
    for _ in range(DAILY_TOPIC_LIMIT):
        database.increment_daily_topic_suggestions(exhausted_id, today)
    for _ in range(MONTHLY_AVATAR_LIMIT):
        database.increment_avatar_generation(exhausted_id, today)

    # Requests for invites waiting in the control panel.
    database.create_invite_request("curious.neighbor@example.com")
    database.create_invite_request("+1 555 0100")

    pooled_count = _seed_pools(database)
    _seed_series(database, rng, skip=existing_topics)

    # Series in every state. A finished series must have no puzzle today, so
    # it goes to a series nobody played today and its unplayed puzzle is
    # removed; a series on its last puzzle keeps today's.
    def played_today(topic_slug: str, difficulty: str) -> bool:
        return database.execute_readonly_query(
            "SELECT COUNT(*) FROM games "
            f"WHERE date = '{today.isoformat()}' AND topic_slug = '{topic_slug}' AND difficulty = '{difficulty}'"
        )["rows"][0][0] > 0

    available = [
        (topic_slug, difficulty) for topic_slug in topic_slugs for difficulty in difficulties
        if database.get_series_status(topic_slug, difficulty) == "available"
    ]
    unplayed = [key for key in available if not played_today(*key)]
    played = [key for key in available if played_today(*key)]
    states: dict[str, tuple[str, str]] = {}
    # A whole topic finished: its only offered series, if nobody played it today.
    for key in unplayed:
        others = [
            database.get_series_status(key[0], difficulty)
            for difficulty in difficulties if difficulty != key[1]
        ]
        if all(status == "unavailable" for status in others):
            states["topic_finished"] = key
            unplayed.remove(key)
            break
    if unplayed:
        states["finished"] = unplayed.pop()
    if played:
        states["last_puzzle"] = played.pop()
    remaining = unplayed + played
    if remaining:
        states["winding_down"] = remaining.pop()
    if remaining:
        states["flagged"] = remaining.pop()

    for state in ("finished", "topic_finished"):
        if state in states:
            database.delete_unplayed_puzzle(today, *states[state])
            database.trim_pool(*states[state], keep=0)
            database.set_series_status(*states[state], "finished")
    if "last_puzzle" in states:
        database.trim_pool(*states["last_puzzle"], keep=0)
        database.set_series_status(*states["last_puzzle"], "winding_down")
    if "winding_down" in states:
        database.trim_pool(*states["winding_down"], keep=8)
        database.set_series_status(*states["winding_down"], "winding_down")
    if "flagged" in states:
        database.set_series_attention(
            *states["flagged"], "Refill failed twice: example flag seeded by the sandbox",
        )

    # Topics date from the start of the history, except the last extra topic,
    # which stays new so the New tag has an example.
    history_start = datetime.combine(today - timedelta(days=history_days), datetime.min.time(), timezone.utc)
    newest_slug = slugify(EXTRA_TOPICS[-1])
    for topic in database.get_all_topics():
        if topic["slug"] not in (newest_slug, BUILDING_TOPIC[0], *existing_topics):
            fixups.topics.append((history_start.isoformat(), topic["slug"]))
    database.close()
    _apply_timestamp_fixups(db_path, fixups)

    return {
        "admin_username": ADMIN_USERNAME,
        "admin_user_id": admin_id,
        "friend_usernames": [username for username, _ in FRIEND_PERSONAS[:friend_count]],
        "anonymous_username": ANONYMOUS_FRIEND[0],
        "follower_username": FOLLOWER_ONLY[0],
        "friend_of_friend_username": FRIEND_OF_FRIEND[0],
        "topic_slugs": topic_slugs,
        "game_count": game_count,
        "puzzle_count": len(puzzle_solutions),
        "pooled_count": pooled_count,
        "history_days": history_days,
        "invite_code": invite_code,
        "series_states": states,
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
    finished: bool = True,
    question_count: Optional[int] = None,
    decoys: Optional[list[str]] = None,
    reveal_hints: bool = True,
    hint_count: Optional[int] = None,
) -> str:
    """Fabricate one game with a plausible transcript. Returns its share code.

    Unfinished games stop after `question_count` questions (default: a
    random handful) with no guess at the solution. For finished games,
    `question_count` fixes the total number of questions, including the
    winning guess. `hint_count` fixes how many hints were revealed (as far
    as the questions unlock them). Topics without hand-written questions
    (e.g. ones suggested on a live sandbox) get generic ones, and `decoys`
    overrides the wrong guesses.
    """
    question_pool = QUESTION_POOLS.get(topic_slug, GENERIC_QUESTIONS)
    if decoys is None:
        decoys = DECOY_GUESSES.get(topic_slug, [])

    if not finished:
        count = question_count or rng.randint(3, 7)
        transcript = rng.sample(question_pool, min(count, len(question_pool)))
        win = False
    elif question_count is not None:
        # An exact length, e.g. a one-question win or all 21 used up.
        candidates = list(question_pool) + [
            question for question in GENERIC_QUESTIONS if question not in question_pool
        ] + [(f"Is it {decoy}?", "no", f"It is not {decoy}.") for decoy in decoys]
        rng.shuffle(candidates)
        transcript = candidates[:question_count - 1 if win else question_count]
    else:
        transcript = rng.sample(question_pool, rng.randint(5, min(12, len(question_pool))))
    if finished and question_count is None:
        guess_count = rng.randint(1, 3) if win else rng.randint(2, 5)
        wrong_guesses = [
            (f"Is it {decoy}?", "no", f"It is not {decoy}.")
            for decoy in rng.sample(decoys, min(guess_count, len(decoys)))
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

    # A hint unlocks every 4 questions; reveal some of the unlocked ones.
    hints_unlocked = min(len(transcript) // 4, 5)
    if hint_count is not None:
        hints_to_reveal = min(hint_count, hints_unlocked)
    elif reveal_hints and hints_unlocked > 0 and rng.random() < 0.5:
        hints_to_reveal = rng.randint(1, min(3, hints_unlocked))
    else:
        hints_to_reveal = 0
    if hints_to_reveal > 0:
        revealed_at = started_at
        for hint_index in range(hints_to_reveal):
            after_question = (hint_index + 1) * 4
            revealed_at += timedelta(seconds=rng.randint(60, 300))
            database.record_hint_reveal(game_id, hint_index, after_question)
            fixups.hint_reveals.append((revealed_at.isoformat(), game_id, hint_index))

    if finished:
        database.end_game(game_id, "win" if win else "loss")
        ended_at = asked_at + timedelta(seconds=rng.randint(3, 20))
        fixups.games.append((started_at.isoformat(), ended_at.isoformat(), game_id))
    else:
        fixups.games.append((started_at.isoformat(), None, game_id))
    return game["share_code"]


# For each persona and each of today's puzzles they haven't played: the
# chance they solve it, fail it, start it without finishing, or skip it.
ACTIVITY_OUTCOMES = (("win", 0.5), ("loss", 0.2), ("in_progress", 0.1), ("skip", 0.2))


def _today_in(time_zone: Optional[str]) -> date:
    if not time_zone:
        return date.today()
    return datetime.now(ZoneInfo(time_zone)).date()


def add_activity(
    db_path: Path,
    *,
    rng_seed: Optional[int] = None,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """Add games for today by every persona except admin, to an existing sandbox.

    Nothing is reset: for each persona, every one of today's puzzles they
    haven't played yet is independently solved, failed, started without
    finishing or skipped, per ACTIVITY_OUTCOMES. Puzzles nobody has drawn
    yet today are drawn from the pool, as a
    real first player would; their hints are generated when someone plays
    them for real. Returns a summary dict.
    """
    rng = random.Random(rng_seed)
    fixups = _TimestampFixups()
    now = datetime.now(timezone.utc)
    database = GameDatabase(db_path)
    database.ensure_schema()
    if today is None:
        # Today in admin's time zone, so the activity lands on their day.
        admin = database.get_account_by_username(ADMIN_USERNAME)
        today = _today_in(admin["time_zone"] if admin else None)

    personas = [
        account for account in database.get_all_accounts()
        if account["username"] != ADMIN_USERNAME
    ]
    series = [
        (topic["slug"], difficulty)
        for topic in database.get_topics_with_status("ready")
        for difficulty in ("normal", "expert")
        if database.get_series_status(topic["slug"], difficulty) in ("available", "winding_down")
    ]

    def todays_solution(topic_slug: str, difficulty: str) -> Optional[str]:
        solution = database.get_puzzle_solution(today, topic_slug, difficulty)
        if solution is None:
            solution = database.draw_puzzle(today, topic_slug, difficulty)
        return solution

    outcomes = [outcome for outcome, _ in ACTIVITY_OUTCOMES]
    weights = [weight for _, weight in ACTIVITY_OUTCOMES]
    added: list[dict[str, str]] = []
    for account in personas:
        unplayed = [
            one_series for one_series in series
            if database.get_existing_game(account["user_id"], today, *one_series) is None
        ]
        for topic_slug, difficulty in unplayed:
            outcome = rng.choices(outcomes, weights)[0]
            if outcome == "skip":
                continue
            solution = todays_solution(topic_slug, difficulty)
            if solution is None:
                continue
            decoys = [
                known for known in database.get_all_known_solutions(topic_slug) if known != solution
            ]
            share_code = _seed_game(
                database, rng, fixups, now,
                user_id=account["user_id"], day=today, topic_slug=topic_slug,
                difficulty=difficulty, solution=solution,
                win=outcome == "win", finished=outcome != "in_progress",
                decoys=decoys or None,
                reveal_hints=bool(database.get_puzzle_hints(today, topic_slug, difficulty)),
            )
            added.append({
                "username": account["username"], "topic_slug": topic_slug,
                "difficulty": difficulty, "outcome": outcome, "share_code": share_code,
            })

    database.close()
    _apply_timestamp_fixups(db_path, fixups)
    return {"date": today.isoformat(), "games": added}


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
        connection.executemany(
            "UPDATE topics SET created_at = ? WHERE slug = ?",
            fixups.topics,
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
        "--keep-data", action="store_true",
        help="Add the sandbox's personas, topics and history to an existing instance's "
             "database (in --dir) instead of recreating it",
    )
    parser.add_argument(
        "--time-zone",
        help="admin's time zone (e.g. America/New_York), which sets the sandbox's today "
             "(default: the system's)",
    )
    parser.add_argument(
        "--add-activity", action="store_true",
        help="Add today's games for every persona except admin to the existing sandbox, then exit",
    )
    parser.add_argument(
        "--generate-pools", action="store_true",
        help="Regenerate the committed sandbox puzzle pools via the LLM, then exit",
    )
    parser.add_argument(
        "--generate-samples", action="store_true",
        help="Regenerate the committed sample avatars via the image API, then exit",
    )
    args = parser.parse_args()

    if args.generate_samples:
        _generate_samples()
        return
    if args.generate_pools:
        _generate_pools()
        return

    sandbox_dir = Path(args.dir).resolve()
    db_path = sandbox_dir.joinpath("data", "h21", "h21.db")

    if args.add_activity:
        if not db_path.is_file():
            print(f"No sandbox at {sandbox_dir}. Create one first.", file=sys.stderr)
            sys.exit(1)
        summary = add_activity(db_path)
        print(f"Added {len(summary['games'])} games for {summary['date']}:")
        for game in summary["games"]:
            outcome = {"win": "solved", "loss": "not solved", "in_progress": "in progress"}[game["outcome"]]
            link = f"  /replay?code={game['share_code']}" if game["outcome"] != "in_progress" else ""
            print(f"  {game['username']:8} {game['topic_slug']} ({game['difficulty']}): {outcome}{link}")
        return

    if args.keep_data:
        if not db_path.is_file():
            print(f"No database at {db_path}.", file=sys.stderr)
            sys.exit(1)
        summary = seed_database(
            db_path, password=args.password, friend_count=args.friends,
            history_days=args.days, rng_seed=args.seed, time_zone=args.time_zone,
        )
        print(f"Added {summary['game_count']} games and {summary['puzzle_count']} puzzles to {db_path}.")
        return

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
            time_zone=args.time_zone,
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
          f"over {summary['history_days']} days, with {summary['pooled_count']} "
          f"pre-generated solutions in the puzzle pools.")
    print()
    print(f"Accounts (password for all: {password!r}):")
    print(f"  {summary['admin_username']:12s} your account (role: admin)")
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
