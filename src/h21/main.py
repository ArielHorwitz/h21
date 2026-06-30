from __future__ import annotations

import logging
import logging.handlers
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger("h21")

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from h21.auth import (
    _ensure_signing_secret,
    clear_session_cookie,
    get_session_user_id,
    set_session_cookie,
)
from h21.config import load_config, _data_dir
from h21.db import GameDatabase, VALID_DIFFICULTIES, slugify
from h21.llm import (
    LLMError,
    OpenAIClient,
    ask_question,
    generate_hints,
    generate_solution,
    normalize_topic,
)

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

# Routes that don't require authentication.
PUBLIC_PATHS = frozenset({"/login", "/api/login", "/api/register"})
PUBLIC_PREFIXES = ("/static/",)


class AskRequest(BaseModel):
    question: str
    game_id: Optional[int] = None
    question_number: Optional[int] = None


class NewGameRequest(BaseModel):
    topic_slug: str = "western-history"
    difficulty: str = "medium"


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
database: GameDatabase
signing_secret: str


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global llm_client, database, signing_secret

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
    llm_client = OpenAIClient(config.openai_api_key, model=config.model)
    database = GameDatabase(config.db_path)
    signing_secret = _ensure_signing_secret(_data_dir())
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


DEV_PATHS = ("/control", "/api/invites", "/api/accounts")


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
    today = date.today()
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
    puzzle_date: date, topic_slug: str, difficulty: str, solution: str
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

    role = database.consume_invite(invite_code)
    if role is None:
        raise HTTPException(status_code=400, detail="Invalid or exhausted invite code")

    try:
        user_id = database.create_account(username, password, role=role, invite_code=invite_code)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Username already taken")

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
    return {
        "user_id": account["user_id"],
        "username": account["username"],
        "role": account["role"],
    }


# -- Invite management (dev only, protected by middleware) --

class CreateInviteRequest(BaseModel):
    alias: Optional[str] = None
    uses: int = 1
    role: str = "user"


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
    code = database.create_invite(alias=alias, uses=request_body.uses, role=request_body.role)
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
    return database.get_all_accounts()


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


# -- Topic endpoints --

@app.get("/api/topics")
async def get_topics() -> list[dict[str, str]]:
    return database.get_all_topics()


@app.post("/api/topics")
async def create_topic(request_body: NewTopicRequest) -> dict[str, str]:
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

    database.add_topic(slug, name)
    return {"slug": slug, "name": name}


# -- Game endpoints --

@app.post("/api/game/new")
async def new_game(request_body: NewGameRequest, request: Request) -> dict[str, int]:
    if request_body.difficulty not in VALID_DIFFICULTIES:
        raise HTTPException(
            status_code=400,
            detail=f"Difficulty must be one of: {', '.join(sorted(VALID_DIFFICULTIES))}",
        )
    if not database.topic_exists(request_body.topic_slug):
        raise HTTPException(status_code=404, detail="Topic not found")

    await get_today_solution(request_body.topic_slug, request_body.difficulty)
    today = date.today()
    user_id = request.state.user_id
    game_id = database.create_game(today, request_body.topic_slug, request_body.difficulty, user_id=user_id)
    return {"game_id": game_id}


@app.post("/api/game/end")
async def end_game(request_body: EndGameRequest) -> dict[str, str]:
    if request_body.result not in ("win", "loss"):
        raise HTTPException(status_code=400, detail="Result must be 'win' or 'loss'")

    game = database.get_game(request_body.game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    database.end_game(request_body.game_id, request_body.result)

    solution = database.get_puzzle_solution(
        date.today(), game["topic_slug"], game["difficulty"],
    )
    return {"status": "ok", "solution": solution or ""}


@app.post("/api/ask")
async def ask(request_body: AskRequest) -> dict[str, str]:
    question = request_body.question.strip()
    if not question or len(question) > 500:
        raise HTTPException(status_code=400, detail="Question must be 1-500 characters")

    # Look up topic + difficulty from the game session.
    topic_slug = "western-history"
    difficulty = "medium"
    if request_body.game_id is not None:
        game = database.get_game(request_body.game_id)
        if game is not None:
            topic_slug = game["topic_slug"]
            difficulty = game["difficulty"]

    secret_solution = await get_today_solution(topic_slug, difficulty)
    topic_name = database.get_topic_name(topic_slug) or topic_slug

    try:
        result = await ask_question(llm_client, question, secret_solution, topic_name)
    except LLMError as exc:
        logger.error("Failed to answer question: %s", exc)
        raise HTTPException(status_code=502, detail=exc.detail)

    if result is None:
        raise HTTPException(
            status_code=502,
            detail="AI returned an unparseable response. Please try again.",
        )

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
            )

    return {"answer": result.answer, "explanation": result.explanation}


class HintRequest(BaseModel):
    game_id: int
    hint_index: int


@app.post("/api/hint")
async def get_hint(request_body: HintRequest) -> dict[str, Any]:
    if request_body.hint_index < 0 or request_body.hint_index > 4:
        raise HTTPException(status_code=400, detail="hint_index must be 0-4")

    game = database.get_game(request_body.game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    required_questions = (request_body.hint_index + 1) * 4
    if game["questions_asked"] < required_questions:
        raise HTTPException(
            status_code=403,
            detail=f"Must have asked at least {required_questions} questions to unlock this hint",
        )

    today = date.today()
    hints = database.get_puzzle_hints(today, game["topic_slug"], game["difficulty"])
    if request_body.hint_index >= len(hints):
        raise HTTPException(status_code=404, detail="Hint not available")

    return {"hint": hints[request_body.hint_index], "hint_index": request_body.hint_index}


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

    uvicorn.run(app, host=host, port=port)
