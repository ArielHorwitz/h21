from __future__ import annotations

import collections
import logging
import logging.handlers
import sqlite3
from contextlib import asynccontextmanager
from datetime import date as date_type, datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger("h21")

import base64

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from h21.auth import (
    _ensure_signing_secret,
    clear_session_cookie,
    get_session_user_id,
    set_session_cookie,
)
from openai import AsyncOpenAI

from h21 import avatar as avatar_mod
from h21.config import load_config, _data_dir
from h21.db import GameDatabase, VALID_DIFFICULTIES, slugify
from h21.llm import (
    GameHistoryEntry,
    HintReveal,
    LLMError,
    OpenAIClient,
    ask_question,
    generate_hints,
    generate_solution,
    normalize_topic,
)

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

# Routes that don't require authentication.
PUBLIC_PATHS = frozenset({"/login", "/api/login", "/api/register", "/api/invite-request", "/api/invite-request-hint"})
PUBLIC_PREFIXES = ("/static/", "/avatars/")


class AskRequest(BaseModel):
    question: str
    game_id: Optional[int] = None
    question_number: Optional[int] = None


class NewGameRequest(BaseModel):
    topic_slug: str = "notable-people"
    difficulty: str = "normal"


class EndGameRequest(BaseModel):
    game_id: int
    result: str  # "win" or "loss"


class NewTopicRequest(BaseModel):
    name: str


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    invite_code: str


# -- app state populated during lifespan --

llm_client: OpenAIClient
openai_image_client: AsyncOpenAI
database: GameDatabase
signing_secret: str
invite_request_hint: str
default_daily_question_limit: int
default_daily_topic_limit: int
default_monthly_avatar_limit: int
avatar_image_model: str
data_dir: Path
log_path: Path


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global llm_client, openai_image_client, database, signing_secret
    global invite_request_hint
    global default_daily_question_limit, default_daily_topic_limit
    global default_monthly_avatar_limit, avatar_image_model, data_dir, log_path

    config = load_config()

    log_format = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(log_format)
    root_logger.addHandler(stderr_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        config.log_path, maxBytes=5 * 1024 * 1024, backupCount=3,
    )
    file_handler.setFormatter(log_format)
    root_logger.addHandler(file_handler)

    logger.info("Logging to %s", config.log_path)
    llm_client = OpenAIClient(
        config.openai_api_key,
        model=config.model,
        reasoning_effort=config.reasoning_effort,
    )
    openai_image_client = AsyncOpenAI(api_key=config.openai_api_key)
    database = GameDatabase(config.db_path)
    data_dir = _data_dir()
    signing_secret = _ensure_signing_secret(data_dir)
    invite_request_hint = config.invite_request_hint
    default_daily_question_limit = config.default_daily_question_limit
    default_daily_topic_limit = config.default_daily_topic_limit
    default_monthly_avatar_limit = config.default_monthly_avatar_limit
    avatar_image_model = config.avatar_image_model
    log_path = config.log_path
    database.ensure_schema()
    yield
    database.close()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/") or not path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


DEV_PATHS = ("/control", "/api/invites", "/api/accounts", "/api/query", "/api/invite-requests", "/api/logs")


@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return await call_next(request)

    user_id = get_session_user_id(request, signing_secret)
    if user_id is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return RedirectResponse("/login", status_code=302)

    account = database.get_account_by_id(user_id)
    if account is None or account["blocked"]:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return RedirectResponse("/login", status_code=302)

    request.state.user_id = user_id
    request.state.role = account["role"]

    if any(path.startswith(prefix) for prefix in DEV_PATHS):
        if account["role"] != "dev":
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Forbidden"}, status_code=403)
            return RedirectResponse("/", status_code=302)

    return await call_next(request)


async def get_today_solution(topic_slug: str, difficulty: str) -> str:
    """Return today's solution for a given topic+difficulty, generating via LLM if needed."""
    today = date_type.today()
    existing = database.get_puzzle_solution(today, topic_slug, difficulty)
    if existing is not None:
        await ensure_hints_exist(today, topic_slug, difficulty, existing)
        return existing

    topic_name = database.get_topic_name(topic_slug)
    if topic_name is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    previous_solutions = database.get_all_solutions(topic_slug, difficulty)
    try:
        solution = await generate_solution(
            llm_client, previous_solutions, topic_name, difficulty,
        )
    except LLMError as exc:
        logger.error("Failed to generate solution: %s", exc)
        raise HTTPException(status_code=502, detail=exc.detail)

    try:
        hints = await generate_hints(llm_client, topic_name, solution)
    except LLMError as exc:
        logger.error("Failed to generate hints: %s", exc)
        hints = []

    database.record_puzzle(today, topic_slug, difficulty, solution, hints=hints)
    return solution


async def ensure_hints_exist(
    puzzle_date: date_type, topic_slug: str, difficulty: str, solution: str
) -> None:
    """Backfill hints for puzzles that were created before the hints feature."""
    existing_hints = database.get_puzzle_hints(puzzle_date, topic_slug, difficulty)
    if existing_hints:
        return
    topic_name = database.get_topic_name(topic_slug)
    if topic_name is None:
        return
    try:
        hints = await generate_hints(llm_client, topic_name, solution)
    except LLMError as exc:
        logger.error("Failed to backfill hints: %s", exc)
        return
    database.update_puzzle_hints(puzzle_date, topic_slug, difficulty, hints)


# -- Page routes --

@app.get("/")
async def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "home.html")


@app.get("/game")
async def game_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/account")
async def account_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "account.html")


@app.get("/help")
async def help_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "help.html")


@app.get("/control")
async def control_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "control.html")


@app.get("/replay")
async def replay_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "replay.html")


@app.get("/leaderboard")
async def leaderboard_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "leaderboard.html")


@app.get("/login")
async def login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "login.html")


# -- Auth endpoints --

@app.post("/api/register")
async def register(request_body: RegisterRequest) -> JSONResponse:
    username = request_body.username.strip()
    password = request_body.password

    if not username or len(username) > 40:
        raise HTTPException(status_code=400, detail="Username must be 1-40 characters")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    invite_code = request_body.invite_code.strip().upper()

    invite = database.consume_invite(invite_code)
    if invite is None:
        raise HTTPException(status_code=400, detail="Invalid or exhausted invite code")

    try:
        question_limit = invite["daily_question_limit"] if invite["daily_question_limit"] is not None else default_daily_question_limit
        topic_limit = invite["daily_topic_limit"] if invite["daily_topic_limit"] is not None else default_daily_topic_limit
        avatar_limit = invite["monthly_avatar_limit"] if invite["monthly_avatar_limit"] is not None else default_monthly_avatar_limit
        user_id = database.create_account(
            username, password, role=invite["role"], invite_code=invite_code,
            daily_question_limit=question_limit,
            daily_topic_limit=topic_limit,
            monthly_avatar_limit=avatar_limit,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Username already taken")

    # Auto-generate a profile picture in the background (best-effort).
    account = database.get_account_by_id(user_id)
    if account and account["player_code"]:
        try:
            image_bytes = await avatar_mod.generate_auto_avatar(
                openai_image_client, avatar_image_model,
            )
            avatar_mod.save_avatar_direct(
                data_dir, account["player_code"], image_bytes,
            )
            database.bump_avatar_version(user_id)
        except Exception:
            logger.exception("Failed to auto-generate avatar for user %s", username)

    response = JSONResponse({"user_id": user_id, "username": username})
    set_session_cookie(response, user_id, signing_secret)
    return response


@app.post("/api/login")
async def login(request_body: LoginRequest) -> JSONResponse:
    username = request_body.username.strip()
    user_id = database.authenticate(username, request_body.password)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    response = JSONResponse({"user_id": user_id, "username": username})
    set_session_cookie(response, user_id, signing_secret)
    return response


@app.post("/api/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"status": "ok"})
    clear_session_cookie(response)
    return response


@app.get("/api/me")
async def get_me(request: Request) -> dict[str, Any]:
    user_id = request.state.user_id
    account = database.get_account_by_id(user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    usage = database.get_daily_usage(user_id, date_type.today())
    avatar_usage = database.get_avatar_usage(user_id, date_type.today())
    return {
        "user_id": account["user_id"],
        "username": account["username"],
        "role": account["role"],
        "daily_question_limit": account["daily_question_limit"],
        "daily_topic_limit": account["daily_topic_limit"],
        "questions_used_today": usage["questions_used"],
        "topic_suggestions_used_today": usage["topic_suggestions_used"],
        "display_name": account["display_name"],
        "player_code": account["player_code"],
        "anonymous": bool(account["anonymous"]),
        "avatar_version": account["avatar_version"],
        "avatar_generations_used": avatar_usage["used"],
        "monthly_avatar_limit": avatar_usage["limit"],
    }


# -- Profile & Friends endpoints --

class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    anonymous: Optional[bool] = None


@app.patch("/api/me")
async def update_me(request_body: UpdateProfileRequest, request: Request) -> dict[str, str]:
    user_id = request.state.user_id
    account = database.get_account_by_id(user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    # Resolve current values for fields not provided.
    display_name = account["display_name"]
    anonymous = bool(account["anonymous"])

    if request_body.display_name is not None:
        display_name = request_body.display_name.strip() or None
        if display_name is not None and len(display_name) > 40:
            raise HTTPException(
                status_code=400, detail="Display name must be 1-40 characters"
            )
    elif "display_name" in (request_body.model_fields_set or set()):
        # Explicitly set to null.
        display_name = None

    if request_body.anonymous is not None:
        anonymous = request_body.anonymous

    database.update_profile(user_id, display_name, anonymous)
    return {"status": "ok"}


@app.get("/api/players/search")
async def search_players(request: Request, q: str = "") -> list[dict[str, Any]]:
    user_id = request.state.user_id
    account = database.get_account_by_id(user_id)
    if account and account["anonymous"]:
        raise HTTPException(status_code=403, detail="Social features are disabled in anonymous mode")
    if len(q) < 1:
        raise HTTPException(status_code=400, detail="Query must be at least 1 character")
    results = database.search_players(q, exclude_user_id=user_id)
    return [
        {"username": row["username"], "display_name": row["display_name"],
         "player_code": row["player_code"],
         "avatar_version": row.get("avatar_version", 0)}
        for row in results
    ]


@app.get("/api/players/{player_code}")
async def get_player(player_code: str, request: Request) -> dict[str, Any]:
    user_id = request.state.user_id
    account = database.get_account_by_id(user_id)
    if account and account["anonymous"]:
        raise HTTPException(status_code=403, detail="Social features are disabled in anonymous mode")
    target = database.get_account_by_player_code(player_code.upper())
    if target is None or target["anonymous"]:
        raise HTTPException(status_code=404, detail="Player not found")
    return {
        "username": target["username"],
        "display_name": target["display_name"],
        "player_code": target["player_code"],
    }


@app.get("/api/friends")
async def list_friends(request: Request) -> list[dict[str, Any]]:
    user_id = request.state.user_id
    account = database.get_account_by_id(user_id)
    if account and account["anonymous"]:
        return []
    friends = database.get_friends(user_id)
    return [
        {"username": friend["username"], "display_name": friend["display_name"],
         "player_code": friend["player_code"],
         "avatar_version": friend.get("avatar_version", 0),
         "anonymous": bool(friend["anonymous"])}
        for friend in friends
    ]


@app.post("/api/friends/{player_code}")
async def follow_player(player_code: str, request: Request) -> dict[str, str]:
    user_id = request.state.user_id
    account = database.get_account_by_id(user_id)
    if account and account["anonymous"]:
        raise HTTPException(status_code=403, detail="Social features are disabled in anonymous mode")
    target = database.get_account_by_player_code(player_code.upper())
    if target is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if target["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")
    if not database.add_friend(user_id, target["user_id"]):
        raise HTTPException(status_code=409, detail="Already following this player")
    return {"status": "ok"}


@app.delete("/api/friends/{player_code}")
async def unfollow_player(player_code: str, request: Request) -> dict[str, str]:
    target = database.get_account_by_player_code(player_code.upper())
    if target is None:
        raise HTTPException(status_code=404, detail="Player not found")
    user_id = request.state.user_id
    if not database.remove_friend(user_id, target["user_id"]):
        raise HTTPException(status_code=404, detail="Not following this player")
    return {"status": "ok"}


# -- Avatar endpoints --

MAX_AVATAR_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@app.post("/api/avatar/generate")
async def generate_avatar(
    request: Request,
    prompt: str = Form(default=""),
    reference: UploadFile = File(default=None),
) -> dict[str, Any]:
    user_id = request.state.user_id
    account = database.get_account_by_id(user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    today = date_type.today()
    avatar_usage = database.get_avatar_usage(user_id, today)
    if avatar_usage["used"] >= avatar_usage["limit"]:
        raise HTTPException(
            status_code=429,
            detail="Monthly avatar generation limit reached",
        )

    prompt_text = prompt.strip() or None
    reference_bytes = None

    if not prompt_text and reference is None:
        raise HTTPException(
            status_code=400,
            detail="Provide a prompt, a reference image, or both",
        )

    if reference is not None:
        reference_bytes = await reference.read()
        if len(reference_bytes) > MAX_AVATAR_UPLOAD_BYTES:
            raise HTTPException(
                status_code=400,
                detail="Reference image must be under 10 MB",
            )
        if len(reference_bytes) == 0:
            reference_bytes = None

    player_code = account["player_code"]
    try:
        image_bytes = await avatar_mod.generate_avatar(
            openai_image_client,
            avatar_image_model,
            prompt=prompt_text,
            reference_image=reference_bytes,
        )
    except Exception as exc:
        logger.error("Avatar generation failed for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to generate avatar. Try a different prompt.",
        )

    database.increment_avatar_generation(user_id, today)

    thumbnail_bytes = avatar_mod.save_pending(data_dir, player_code, image_bytes)

    avatar_usage = database.get_avatar_usage(user_id, today)
    return {
        "original_b64": base64.b64encode(image_bytes).decode(),
        "thumbnail_b64": base64.b64encode(thumbnail_bytes).decode(),
        "generations_used": avatar_usage["used"],
        "monthly_avatar_limit": avatar_usage["limit"],
    }


@app.post("/api/avatar/confirm")
async def confirm_avatar(request: Request) -> dict[str, Any]:
    user_id = request.state.user_id
    account = database.get_account_by_id(user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    player_code = account["player_code"]
    if not avatar_mod.confirm_pending(data_dir, player_code):
        raise HTTPException(status_code=404, detail="No pending avatar to confirm")

    new_version = database.bump_avatar_version(user_id)
    return {"status": "ok", "avatar_version": new_version}


@app.post("/api/avatar/discard")
async def discard_avatar(request: Request) -> dict[str, str]:
    user_id = request.state.user_id
    account = database.get_account_by_id(user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    avatar_mod.discard_pending(data_dir, account["player_code"])
    return {"status": "ok"}


@app.get("/avatars/{player_code}.webp")
async def serve_avatar_thumbnail(player_code: str) -> Response:
    path = avatar_mod.get_thumbnail_path(data_dir, player_code.upper())
    if path is None:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


@app.get("/avatars/{player_code}_original.png")
async def serve_avatar_original(player_code: str) -> Response:
    path = avatar_mod.get_original_path(data_dir, player_code.upper())
    if path is None:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return FileResponse(
        path,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


# -- Recap --

def _compute_score(questions_asked: int, hints_used: int) -> int:
    return questions_asked + hints_used * 50


def _select_friends_for_result(
    player_score: int, friends: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Select up to 3 friends for a recent results game entry.

    If the player is NOT the top performer: show the top performer + 2 closest.
    If the player IS the top performer: show the 3 closest below.
    """
    if not friends:
        return []

    # Compute scores and sort friends by score (best first).
    scored_friends = []
    for friend in friends:
        friend_score = _compute_score(friend["questions_asked"], friend["hints_used"])
        scored_friends.append((friend_score, friend))
    scored_friends.sort(key=lambda entry: (entry[0], entry[1].get("username", "")))

    best_friend_score = scored_friends[0][0]
    player_is_top = player_score <= best_friend_score

    if player_is_top:
        # Show 3 closest to player's score (all are below or equal).
        by_distance = sorted(
            scored_friends,
            key=lambda entry: (abs(entry[0] - player_score), entry[1].get("username", "")),
        )
        return [entry[1] for entry in by_distance[:3]]
    else:
        # Top performer + 2 closest to player's score (excluding top performer).
        top_friend = scored_friends[0][1]
        remaining = scored_friends[1:]
        by_distance = sorted(
            remaining,
            key=lambda entry: (abs(entry[0] - player_score), entry[1].get("username", "")),
        )
        closest = [entry[1] for entry in by_distance[:2]]
        return [top_friend] + closest


@app.get("/api/recent-results")
async def get_recent_results(request: Request) -> list[dict[str, Any]]:
    user_id = request.state.user_id
    recent_results = database.get_recent_results(user_id, limit=3)

    result = []
    for game in recent_results:
        player_score = _compute_score(game["questions_asked"], game["hints_used"])

        selected_friends = _select_friends_for_result(player_score, game["friends"])

        # Build friend response objects with display_name fallback.
        friend_entries = []
        for friend in selected_friends:
            friend_entries.append({
                "display_name": friend["display_name"] or friend["username"],
                "player_code": friend["player_code"],
                "avatar_version": friend.get("avatar_version", 0),
                "questions_asked": friend["questions_asked"],
                "hints_used": friend["hints_used"],
            })

        result.append({
            "topic_name": game["topic_name"],
            "topic_slug": game["topic_slug"],
            "difficulty": game["difficulty"],
            "date": game["date"],
            "my_result": {
                "questions_asked": game["questions_asked"],
                "hints_used": game["hints_used"],
            },
            "friends": friend_entries,
        })

    return result


@app.get("/api/play-next")
async def get_play_next(request: Request) -> list[dict[str, Any]]:
    user_id = request.state.user_id
    today = date_type.today()
    return database.get_play_next(user_id, today)


def _truncate_leaderboard(
    players: list[dict[str, Any]], limit: int,
) -> list[dict[str, Any]]:
    """Truncate a leaderboard to at most `limit` players.

    Priority order: the viewing user, top 3 performers, all friends, then
    remaining players in rank order. Preserves the original sort order in
    the returned list.
    """
    # Build index sets by priority tier.
    self_indices: set[int] = set()
    top3_indices: set[int] = set()
    friend_indices: set[int] = set()

    for index, player in enumerate(players):
        if player["is_self"]:
            self_indices.add(index)
        if player["rank"] <= 3:
            top3_indices.add(index)
        if player["is_friend"]:
            friend_indices.add(index)

    # Collect indices in priority order, deduplicating.
    kept: list[int] = []
    seen: set[int] = set()

    for index_set in (self_indices, top3_indices, friend_indices):
        for index in sorted(index_set):
            if index not in seen:
                kept.append(index)
                seen.add(index)

    # Fill remaining slots with other players in rank order.
    for index in range(len(players)):
        if len(kept) >= limit:
            break
        if index not in seen:
            kept.append(index)
            seen.add(index)

    # Return in original sort order.
    kept.sort()
    return [players[index] for index in kept]


@app.get("/api/leaderboard")
async def get_leaderboard(
    request: Request, topic_slug: str, difficulty: str, date: str,
) -> dict[str, Any]:
    try:
        puzzle_date = date_type.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    if difficulty not in VALID_DIFFICULTIES:
        raise HTTPException(
            status_code=400,
            detail=f"Difficulty must be one of: {', '.join(sorted(VALID_DIFFICULTIES))}",
        )

    topic_name = database.get_topic_name(topic_slug)
    if topic_name is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    user_id = request.state.user_id
    winners = database.get_puzzle_winners(puzzle_date, topic_slug, difficulty, user_id)

    # Score, sort, and rank.
    scored = []
    for winner in winners:
        score = _compute_score(winner["questions_asked"], winner["hints_used"])
        scored.append((score, winner))
    scored.sort(key=lambda entry: (entry[0], entry[1]["username"] or ""))

    max_players = 60
    players = []
    current_rank = 0
    previous_score = None
    for position, (score, winner) in enumerate(scored, start=1):
        if score != previous_score:
            current_rank = position
            previous_score = score
        players.append({
            "rank": current_rank,
            "display_name": winner["display_name"] or winner["username"],
            "player_code": winner.get("player_code"),
            "avatar_version": winner.get("avatar_version", 0),
            "questions_asked": winner["questions_asked"],
            "hints_used": winner["hints_used"],
            "is_self": winner["user_id"] == user_id,
            "is_friend": bool(winner["is_friend"]),
        })

    if len(players) > max_players:
        players = _truncate_leaderboard(players, max_players)

    return {
        "topic_name": topic_name,
        "topic_slug": topic_slug,
        "difficulty": difficulty,
        "date": date,
        "players": players,
    }


# -- Invite management (dev only, protected by middleware) --

class CreateInviteRequest(BaseModel):
    alias: Optional[str] = None
    uses: int = 1
    role: str = "user"
    daily_question_limit: Optional[int] = None
    daily_topic_limit: Optional[int] = None
    monthly_avatar_limit: Optional[int] = None


@app.get("/api/invites")
async def list_invites() -> list[dict[str, Any]]:
    return database.get_all_invites()


@app.post("/api/invites")
async def create_invite_api(request_body: CreateInviteRequest) -> dict[str, Any]:
    if request_body.role not in ("user", "dev"):
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'dev'")
    if request_body.uses < 1:
        raise HTTPException(status_code=400, detail="Uses must be at least 1")
    alias = request_body.alias.strip() if request_body.alias else None
    code = database.create_invite(
        alias=alias, uses=request_body.uses, role=request_body.role,
        daily_question_limit=request_body.daily_question_limit,
        daily_topic_limit=request_body.daily_topic_limit,
        monthly_avatar_limit=request_body.monthly_avatar_limit,
    )
    invite = database.get_invite(code)
    return invite


@app.delete("/api/invites/{code}")
async def delete_invite_api(code: str) -> dict[str, str]:
    if not database.delete_invite(code.upper()):
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"status": "ok"}


# -- Account management (dev only, protected by middleware) --

@app.get("/api/accounts")
async def list_accounts() -> list[dict[str, Any]]:
    accounts = database.get_all_accounts()
    today = date_type.today()
    for account in accounts:
        usage = database.get_daily_usage(account["user_id"], today)
        account["questions_used_today"] = usage["questions_used"]
        account["topic_suggestions_used_today"] = usage["topic_suggestions_used"]
    return accounts


@app.post("/api/accounts/{user_id}/block")
async def block_account(user_id: int, request: Request) -> dict[str, str]:
    if user_id == request.state.user_id:
        raise HTTPException(status_code=400, detail="Cannot block yourself")
    if not database.set_account_blocked(user_id, blocked=True):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "ok"}


@app.post("/api/accounts/{user_id}/unblock")
async def unblock_account(user_id: int) -> dict[str, str]:
    if not database.set_account_blocked(user_id, blocked=False):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "ok"}


class UpdateLimitsRequest(BaseModel):
    daily_question_limit: int
    daily_topic_limit: int


@app.post("/api/accounts/{user_id}/limits")
async def update_limits(user_id: int, request_body: UpdateLimitsRequest) -> dict[str, str]:
    if request_body.daily_question_limit < 0 or request_body.daily_topic_limit < 0:
        raise HTTPException(status_code=400, detail="Limits must be non-negative")
    if not database.update_account_limits(
        user_id, request_body.daily_question_limit, request_body.daily_topic_limit,
    ):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "ok"}


@app.post("/api/accounts/{user_id}/reset-usage")
async def reset_usage(user_id: int) -> dict[str, str]:
    database.reset_daily_usage(user_id, date_type.today())
    return {"status": "ok"}


# -- Query (dev only) --

class QueryRequest(BaseModel):
    sql: str


@app.post("/api/query")
async def run_query(request_body: QueryRequest) -> dict[str, Any]:
    sql = request_body.sql.strip()
    if not sql:
        raise HTTPException(status_code=400, detail="SQL query must not be empty")
    try:
        result = database.execute_readonly_query(sql)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


# -- Logs (dev only) --

@app.get("/api/logs")
async def get_logs(mode: str = "tail", lines: int = 100) -> dict[str, Any]:
    if mode not in ("head", "tail"):
        raise HTTPException(status_code=400, detail="mode must be 'head' or 'tail'")
    if lines < 1 or lines > 10000:
        raise HTTPException(status_code=400, detail="lines must be between 1 and 10000")

    if not log_path.exists():
        return {"lines": [], "mode": mode}

    with open(log_path, "r", errors="replace") as log_file:
        if mode == "head":
            result_lines = []
            for line_number, line in enumerate(log_file):
                if line_number >= lines:
                    break
                result_lines.append(line.rstrip("\n"))
        else:
            result_lines = [
                line.rstrip("\n")
                for line in collections.deque(log_file, maxlen=lines)
            ]

    return {"lines": result_lines, "mode": mode}


# -- Invite requests --

INVITE_REQUEST_COOLDOWN_SECONDS = 300  # 5 minutes


class InviteRequestBody(BaseModel):
    contact_info: str


@app.get("/api/invite-request-hint")
async def get_invite_request_hint() -> dict[str, str]:
    return {"hint": invite_request_hint}


@app.post("/api/invite-request")
async def request_invite(request_body: InviteRequestBody) -> dict[str, str]:
    contact_info = request_body.contact_info.strip()
    if not contact_info or len(contact_info) > 200:
        raise HTTPException(status_code=400, detail="Contact info must be 1-200 characters")

    latest_time = database.get_latest_invite_request_time()
    if latest_time is not None:
        latest_dt = datetime.fromisoformat(latest_time)
        elapsed = (datetime.now(timezone.utc) - latest_dt).total_seconds()
        if elapsed < INVITE_REQUEST_COOLDOWN_SECONDS:
            remaining = int(INVITE_REQUEST_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {remaining} seconds before submitting another request",
            )

    database.create_invite_request(contact_info)
    return {"status": "ok"}


@app.get("/api/invite-requests")
async def list_invite_requests() -> list[dict[str, Any]]:
    return database.get_all_invite_requests()


@app.delete("/api/invite-requests/{request_id}")
async def delete_invite_request(request_id: int) -> dict[str, str]:
    if not database.delete_invite_request(request_id):
        raise HTTPException(status_code=404, detail="Request not found")
    return {"status": "ok"}


# -- Topic endpoints --

@app.get("/api/topics")
async def get_topics() -> list[dict[str, str]]:
    return database.get_all_topics()


@app.post("/api/topics")
async def create_topic(request_body: NewTopicRequest, request: Request) -> dict[str, str]:
    user_id = request.state.user_id
    account = database.get_account_by_id(user_id)
    usage = database.get_daily_usage(user_id, date_type.today())
    if account and usage["topic_suggestions_used"] >= account["daily_topic_limit"]:
        raise HTTPException(status_code=429, detail="Daily topic suggestion limit reached")

    raw_name = request_body.name.strip()
    if not raw_name or len(raw_name) > 100:
        raise HTTPException(
            status_code=400, detail="Topic name must be 1-100 characters"
        )

    try:
        name = await normalize_topic(llm_client, raw_name)
    except LLMError as exc:
        logger.error("Failed to normalize topic: %s", exc)
        raise HTTPException(status_code=502, detail=exc.detail)
    slug = slugify(name)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid topic name")

    if database.topic_exists(slug):
        raise HTTPException(status_code=409, detail="Topic already exists")

    database.add_topic(slug, name, user_id=user_id)
    database.increment_daily_topic_suggestions(user_id, date_type.today())
    return {"slug": slug, "name": name}


# -- Game endpoints --

@app.get("/api/game/existing")
async def get_existing_game(request: Request, topic_slug: str, difficulty: str) -> JSONResponse:
    user_id = request.state.user_id
    today = date_type.today()
    game = database.get_existing_game(user_id, today, topic_slug, difficulty)
    if game is None:
        return Response(status_code=204)
    return JSONResponse(game)


@app.get("/api/game/statuses")
async def get_game_statuses(request: Request) -> list[dict[str, Any]]:
    user_id = request.state.user_id
    today = date_type.today()
    return database.get_game_statuses(user_id, today)


@app.post("/api/game/new")
async def new_game(request_body: NewGameRequest, request: Request) -> dict[str, Any]:
    if request_body.difficulty not in VALID_DIFFICULTIES:
        raise HTTPException(
            status_code=400,
            detail=f"Difficulty must be one of: {', '.join(sorted(VALID_DIFFICULTIES))}",
        )
    if not database.topic_exists(request_body.topic_slug):
        raise HTTPException(status_code=404, detail="Topic not found")

    today = date_type.today()
    user_id = request.state.user_id
    existing = database.get_existing_game(user_id, today, request_body.topic_slug, request_body.difficulty)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Game already exists for this puzzle")

    await get_today_solution(request_body.topic_slug, request_body.difficulty)
    game = database.create_game(today, request_body.topic_slug, request_body.difficulty, user_id=user_id)
    return {"game_id": game["game_id"], "share_code": game["share_code"]}


@app.post("/api/game/end")
async def end_game(request_body: EndGameRequest, request: Request) -> dict[str, Any]:
    if request_body.result not in ("win", "loss"):
        raise HTTPException(status_code=400, detail="Result must be 'win' or 'loss'")

    game = database.get_game(request_body.game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if game["user_id"] is not None and game["user_id"] != request.state.user_id:
        raise HTTPException(status_code=403, detail="Not your game")
    if game["date"] != date_type.today().isoformat():
        raise HTTPException(status_code=410, detail="This puzzle has expired")

    database.end_game(request_body.game_id, request_body.result)

    today = date_type.today()
    solution = database.get_puzzle_solution(
        today, game["topic_slug"], game["difficulty"],
    )
    hints = database.get_puzzle_hints(today, game["topic_slug"], game["difficulty"])
    return {"status": "ok", "solution": solution or "", "hints": hints}


@app.post("/api/ask")
async def ask(request_body: AskRequest, request: Request) -> dict[str, str]:
    user_id = request.state.user_id
    account = database.get_account_by_id(user_id)
    usage = database.get_daily_usage(user_id, date_type.today())
    if account and usage["questions_used"] >= account["daily_question_limit"]:
        raise HTTPException(status_code=429, detail="Daily question limit reached")

    question = request_body.question.strip()
    if not question or len(question) > 500:
        raise HTTPException(status_code=400, detail="Question must be 1-500 characters")

    # Look up topic + difficulty from the game session.
    topic_slug = "notable-people"
    difficulty = "normal"
    if request_body.game_id is not None:
        game = database.get_game(request_body.game_id)
        if game is not None:
            if game["user_id"] is not None and game["user_id"] != user_id:
                raise HTTPException(status_code=403, detail="Not your game")
            if game["date"] != date_type.today().isoformat():
                raise HTTPException(status_code=410, detail="This puzzle has expired")
            topic_slug = game["topic_slug"]
            difficulty = game["difficulty"]

    secret_solution = await get_today_solution(topic_slug, difficulty)
    topic_name = database.get_topic_name(topic_slug) or topic_slug

    # Build conversation history so the LLM interprets follow-up questions
    # in context of what the player has already asked and been told.
    history: list[GameHistoryEntry] = []
    hint_reveal_context: list[HintReveal] = []
    question_number = request_body.question_number or 1
    if request_body.game_id is not None:
        past_questions = database.get_game_history(request_body.game_id)
        history = [
            GameHistoryEntry(
                question_number=row["question_number"],
                question=row["question"],
                answer=row["answer"],
            )
            for row in past_questions
        ]
        hint_reveals = database.get_hint_reveals(request_body.game_id)
        if hint_reveals:
            today = date_type.today()
            hints = database.get_puzzle_hints(
                today, topic_slug, difficulty,
            )
            hint_reveal_context = [
                HintReveal(
                    after_question=reveal["after_question"],
                    hint_text=hints[reveal["hint_index"]],
                )
                for reveal in hint_reveals
                if reveal["hint_index"] < len(hints)
            ]

    # Reject questions that were already asked verbatim in this game.
    question_lower = question.casefold()
    for entry in history:
        if entry.question.casefold() == question_lower:
            raise HTTPException(
                status_code=409,
                detail="You already asked this question.",
            )

    username = account["username"] if account else f"user:{user_id}"
    game_id = request_body.game_id

    logger.info(
        "User %s asked question #%d in game %s: %r",
        username, question_number, game_id, question,
    )

    try:
        result = await ask_question(
            llm_client, question, secret_solution, topic_name,
            question_number=question_number,
            history=history,
            hint_reveals=hint_reveal_context,
        )
    except LLMError as exc:
        logger.error("Failed to answer question: %s", exc)
        raise HTTPException(status_code=502, detail=exc.detail)

    if result is None:
        raise HTTPException(
            status_code=502,
            detail="AI returned an unparseable response. Please try again.",
        )

    logger.info(
        "User %s got response to question #%d in game %s: %s",
        username, question_number, game_id, result.answer,
    )

    database.increment_daily_questions(user_id, date_type.today())

    # Record the Q&A if a game session is active.
    if request_body.game_id is not None and request_body.question_number is not None:
        game = database.get_game(request_body.game_id)
        if game is not None:
            database.record_question(
                request_body.game_id,
                request_body.question_number,
                question,
                result.answer,
                result.explanation,
                user_id=user_id,
            )

    return {"answer": result.answer, "explanation": result.explanation}


class HintRequest(BaseModel):
    game_id: int
    hint_index: int


@app.post("/api/hint")
async def get_hint(request_body: HintRequest, request: Request) -> dict[str, Any]:
    if request_body.hint_index < 0 or request_body.hint_index > 4:
        raise HTTPException(status_code=400, detail="hint_index must be 0-4")

    game = database.get_game(request_body.game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if game["user_id"] is not None and game["user_id"] != request.state.user_id:
        raise HTTPException(status_code=403, detail="Not your game")
    if game["date"] != date_type.today().isoformat():
        raise HTTPException(status_code=410, detail="This puzzle has expired")

    required_questions = (request_body.hint_index + 1) * 4
    if game["questions_asked"] < required_questions:
        raise HTTPException(
            status_code=403,
            detail=f"Must have asked at least {required_questions} questions to unlock this hint",
        )

    today = date_type.today()
    hints = database.get_puzzle_hints(today, game["topic_slug"], game["difficulty"])
    if request_body.hint_index >= len(hints):
        raise HTTPException(status_code=404, detail="Hint not available")

    database.record_hint_reveal(
        request_body.game_id, request_body.hint_index, game["questions_asked"],
    )

    return {
        "hint": hints[request_body.hint_index],
        "hint_index": request_body.hint_index,
        "after_question": game["questions_asked"],
    }


@app.get("/api/replay/{share_code}")
async def get_replay(share_code: str, request: Request) -> dict[str, Any]:
    game = database.get_game_by_share_code(share_code.upper())
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    # Gate today's puzzles: only allow replay if the viewer has played it.
    today = date_type.today()
    if game["date"] == today.isoformat():
        viewer_id = request.state.user_id
        has_played = database.has_played_puzzle(
            viewer_id, today, game["topic_slug"], game["difficulty"],
        )
        if not has_played:
            raise HTTPException(
                status_code=403,
                detail="Play this puzzle first to view replays from today.",
            )
    # Strip internal fields the client doesn't need.
    game.pop("game_id", None)
    game.pop("started_at", None)
    game.pop("ended_at", None)
    return game


@app.get("/api/history")
async def get_history(request: Request) -> list[dict]:
    user_id = request.state.user_id
    return database.get_history(user_id=user_id)


def cli() -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Run the h21 server")
    parser.add_argument("--public", action="store_true",
                        help="Listen on 0.0.0.0:80 (overridden by --host/--port)")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    host = args.host or ("0.0.0.0" if args.public else "127.0.0.1")
    port = args.port or (80 if args.public else 8000)

    uvicorn.run(app, host=host, port=port, log_config=None)
