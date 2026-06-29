from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from h21.config import load_config
from h21.llm import OpenAIClient, ask_question
from h21.pow import ProofOfWork
from h21.puzzle import Puzzle

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


class AskRequest(BaseModel):
    question: str
    challenge_id: str
    nonce: str


# -- app state populated during lifespan --

puzzle: Puzzle
llm_client: OpenAIClient
proof_of_work: ProofOfWork


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global puzzle, llm_client, proof_of_work

    config = load_config()
    puzzle = Puzzle(config.solutions_file, config.start_date)
    llm_client = OpenAIClient(config.openai_api_key)
    proof_of_work = ProofOfWork(difficulty=config.pow_difficulty)
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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

    return {"answer": response}


def cli() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
