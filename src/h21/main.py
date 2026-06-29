from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from h21.config import load_config
from h21.db import GameDatabase
from h21.llm import OpenAIClient, ask_question
from h21.pow import ProofOfWork
from h21.puzzle import Puzzle

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


class AskRequest(BaseModel):
    question: str
    challenge_id: str
    nonce: str
    game_id: Optional[int] = None
    question_number: Optional[int] = None


class EndGameRequest(BaseModel):
    game_id: int
    result: str  # "win" or "loss"


# -- app state populated during lifespan --

puzzle: Puzzle
llm_client: OpenAIClient
proof_of_work: ProofOfWork
database: GameDatabase


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global puzzle, llm_client, proof_of_work, database

    config = load_config()
    puzzle = Puzzle(config.solutions_file, config.start_date)
    llm_client = OpenAIClient(config.openai_api_key)
    proof_of_work = ProofOfWork(difficulty=config.pow_difficulty)
    database = GameDatabase(config.db_path)
    database.ensure_schema()
    yield
    database.close()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _record_todays_puzzle() -> None:
    """Ensure today's puzzle is recorded in the database."""
    today = date.today()
    solution = puzzle.get_today_solution()
    database.record_puzzle(today, solution)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/challenge")
async def get_challenge() -> dict[str, str | int]:
    challenge_id, challenge = proof_of_work.generate_challenge()
    return {
        "challenge_id": challenge_id,
        "challenge": challenge,
        "difficulty": proof_of_work.difficulty,
    }


@app.post("/api/game/new")
async def new_game() -> dict[str, int]:
    _record_todays_puzzle()
    today = date.today()
    game_id = database.create_game(today)
    return {"game_id": game_id}


@app.post("/api/game/end")
async def end_game(request: EndGameRequest) -> dict[str, str]:
    if request.result not in ("win", "loss"):
        raise HTTPException(status_code=400, detail="Result must be 'win' or 'loss'")

    game = database.get_game(request.game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    database.end_game(request.game_id, request.result)
    return {"status": "ok"}


@app.post("/api/ask")
async def ask(request: AskRequest) -> dict[str, str]:
    if not proof_of_work.verify(request.challenge_id, request.nonce):
        raise HTTPException(status_code=403, detail="Invalid proof of work")

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    secret_solution = puzzle.get_today_solution()
    response = await ask_question(llm_client, question, secret_solution)

    if response is None:
        raise HTTPException(
            status_code=502,
            detail="Could not process the question. Please try again.",
        )

    # Record the Q&A if a game session is active.
    if request.game_id is not None and request.question_number is not None:
        game = database.get_game(request.game_id)
        if game is not None:
            database.record_question(
                request.game_id,
                request.question_number,
                question,
                response,
            )

    return {"answer": response}


@app.get("/api/history")
async def get_history() -> list[dict]:
    return database.get_history()


def cli() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
