from __future__ import annotations

import hmac
import logging
import logging.handlers
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import AsyncIterator, Optional

logger = logging.getLogger("h21")

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from h21.config import load_config
from h21.db import GameDatabase, VALID_DIFFICULTIES, slugify
from h21.llm import (
    AnswerResult,
    LLMError,
    OpenAIClient,
    ask_question,
    generate_solution,
    normalize_topic,
)
from h21.pow import ProofOfWork

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


class AskRequest(BaseModel):
    question: str
    challenge_id: Optional[str] = None
    nonce: Optional[str] = None
    password: Optional[str] = None
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


# -- app state populated during lifespan --

llm_client: OpenAIClient
proof_of_work: ProofOfWork
database: GameDatabase
bypass_password: Optional[str]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global llm_client, proof_of_work, database, bypass_password

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
    proof_of_work = ProofOfWork(difficulty=config.pow_difficulty)
    database = GameDatabase(config.db_path)
    bypass_password = config.bypass_password
    database.ensure_schema()
    yield
    database.close()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


async def get_today_solution(topic_slug: str, difficulty: str) -> str:
    """Return today's solution for a given topic+difficulty, generating via LLM if needed."""
    today = date.today()
    existing = database.get_puzzle_solution(today, topic_slug, difficulty)
    if existing is not None:
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
    database.record_puzzle(today, topic_slug, difficulty, solution)
    return solution


@app.get("/")
async def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "home.html")


@app.get("/game")
async def game_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/settings")
async def settings_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "settings.html")


@app.get("/api/topics")
async def get_topics() -> list[dict[str, str]]:
    return database.get_all_topics()


@app.post("/api/topics")
async def create_topic(request: NewTopicRequest) -> dict[str, str]:
    raw_name = request.name.strip()
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


@app.get("/api/pow-bypass-available")
async def pow_bypass_available() -> dict[str, bool]:
    return {"available": bypass_password is not None}


class ValidatePasswordRequest(BaseModel):
    password: str


@app.post("/api/validate-password")
async def validate_password(request: ValidatePasswordRequest) -> dict[str, bool]:
    """Check whether the given password matches the configured bypass password."""
    if bypass_password is None:
        return {"valid": False, "required": False}
    valid = hmac.compare_digest(request.password, bypass_password)
    return {"valid": valid, "required": True}


@app.get("/api/challenge")
async def get_challenge() -> dict[str, str | int]:
    challenge_id, challenge = proof_of_work.generate_challenge()
    return {
        "challenge_id": challenge_id,
        "challenge": challenge,
        "difficulty": proof_of_work.difficulty,
    }


@app.post("/api/game/new")
async def new_game(request: NewGameRequest) -> dict[str, int]:
    if request.difficulty not in VALID_DIFFICULTIES:
        raise HTTPException(
            status_code=400,
            detail=f"Difficulty must be one of: {', '.join(sorted(VALID_DIFFICULTIES))}",
        )
    if not database.topic_exists(request.topic_slug):
        raise HTTPException(status_code=404, detail="Topic not found")

    await get_today_solution(request.topic_slug, request.difficulty)
    today = date.today()
    game_id = database.create_game(today, request.topic_slug, request.difficulty)
    return {"game_id": game_id}


@app.post("/api/game/end")
async def end_game(request: EndGameRequest) -> dict[str, str]:
    if request.result not in ("win", "loss"):
        raise HTTPException(status_code=400, detail="Result must be 'win' or 'loss'")

    game = database.get_game(request.game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    database.end_game(request.game_id, request.result)

    solution = database.get_puzzle_solution(
        date.today(), game["topic_slug"], game["difficulty"],
    )
    return {"status": "ok", "solution": solution or ""}


@app.post("/api/ask")
async def ask(request: AskRequest) -> dict[str, str]:
    password_valid = (
        bypass_password is not None
        and request.password is not None
        and hmac.compare_digest(request.password, bypass_password)
    )
    if not password_valid:
        if not request.challenge_id or not request.nonce:
            raise HTTPException(status_code=403, detail="Proof of work required")
        if not proof_of_work.verify(request.challenge_id, request.nonce):
            raise HTTPException(status_code=403, detail="Invalid proof of work")

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Look up topic + difficulty from the game session.
    topic_slug = "western-history"
    difficulty = "medium"
    if request.game_id is not None:
        game = database.get_game(request.game_id)
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
    if request.game_id is not None and request.question_number is not None:
        game = database.get_game(request.game_id)
        if game is not None:
            database.record_question(
                request.game_id,
                request.question_number,
                question,
                result.answer,
                result.explanation,
            )

    return {"answer": result.answer, "explanation": result.explanation}


@app.get("/api/history")
async def get_history() -> list[dict]:
    return database.get_history()


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
