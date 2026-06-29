# Initial Implementation Plan

## Project structure

```
h21/
  daily-solutions.txt        # one subject per line (user-curated, already exists)
  config.toml                # start_date, openai api key, PoW difficulty, etc.
  .gitignore
  pyproject.toml
  Dockerfile
  src/
    h21/
      __init__.py
      main.py                # FastAPI app, routes, startup
      llm.py                 # LLM client abstraction + OpenAI implementation
      puzzle.py              # daily answer selection logic
      pow.py                 # proof-of-work challenge/verification
      config.py              # config loading from config.toml
  static/
    index.html               # single-page game UI
    style.css
    game.js                  # game logic, PoW worker spawning
    pow-worker.js            # Web Worker for PoW computation
```

## Components

### 1. Configuration (`config.py`, `config.toml`)

`config.toml` holds:
- `start_date` — the date corresponding to answer index 0 (e.g. `2026-07-01`)
- `openai_api_key` — or read from env var `OPENAI_API_KEY`; env var takes
  precedence
- `pow_difficulty` — number of leading zero bits required (default: 20, ~1s on a
  modern browser)
- `solutions_file` — path to `daily-solutions.txt` (default: `daily-solutions.txt`)

`config.py` loads and validates this at startup using `tomllib`.

### 2. Daily puzzle selection (`puzzle.py`)

- Load solutions from the solutions file (one per line, stripped, blank lines
  ignored).
- `get_today_solution() -> str`: compute
  `(today - start_date).days % len(solutions)` to get the index. Return the
  solution string.
- The solution list is loaded once at startup and cached.

### 3. LLM abstraction (`llm.py`)

Define a protocol:

```python
class LLMClient(Protocol):
    async def ask(self, system_prompt: str, user_message: str) -> str: ...
```

OpenAI implementation using the `openai` async client. Returns raw completion
text.

A wrapper function `ask_question(question: str, secret_answer: str) -> str`:
- Constructs the system prompt with game rules and the secret answer.
- Calls the LLM client.
- Parses the response: strips whitespace, lowercases, checks against the legal
  set `{"yes", "no", "partially", "depends", "win"}`.
- If the response isn't in the legal set, returns a sentinel like `"error"` so
  the route can respond with a generic error to the client.

System prompt (initial version, tunable later):
```
You are the host of a game of 21 questions. The secret answer is: "{answer}".
The answer is a historical figure, event, or place.

The player will ask you questions or make guesses. You must respond with EXACTLY
one word — one of: yes, no, partially, depends, win.

- "yes" if the answer to their question is clearly yes.
- "no" if the answer is clearly no.
- "partially" if the answer is partly correct or context-dependent.
- "depends" if the answer varies based on interpretation or framing.
- "win" ONLY if the player has correctly identified the secret answer.

Do not reveal the answer. Do not explain. Respond with a single word only.
```

### 4. Proof of work (`pow.py`)

**Server side:**
- `generate_challenge() -> tuple[str, str]`: generate a random challenge string
  and return `(challenge_id, challenge_string)`. Store in an in-memory dict with
  a TTL (5 minutes).
- `verify_pow(challenge_id: str, nonce: str, difficulty: int) -> bool`: check
  that `sha256(challenge + nonce)` has `difficulty` leading zero bits, and that
  the challenge hasn't been used or expired.
- Challenges are single-use — consumed on verification.

**Client side (`pow-worker.js`):**
- Receives `(challenge, difficulty)`.
- Brute-forces a nonce (incrementing integer) until `sha256(challenge + nonce)`
  has the required leading zeroes.
- Posts the nonce back to the main thread.

### 5. API routes (`main.py`)

Three endpoints:

1. **`GET /api/challenge`** — returns `{ "challenge_id": "...", "challenge": "..." }`
2. **`POST /api/ask`** — accepts
   `{ "question": "...", "challenge_id": "...", "nonce": "..." }`
   - Verifies PoW.
   - Calls `ask_question()` with the user's question and today's answer.
   - Returns `{ "answer": "yes" | "no" | ... }` or `{ "error": "..." }`.
3. **`GET /`** — serves `static/index.html` (via `StaticFiles` mount or a
   catch-all).

Static files mounted at `/static/`.

### 6. Frontend (`index.html`, `style.css`, `game.js`, `pow-worker.js`)

Simple, clean UI:
- Title/header with today's date.
- A scrollable log of Q&A pairs.
- An input field + submit button.
- A question counter ("Question 5 of 21").
- On submit: fetch a PoW challenge, solve it in the web worker, then POST to
  `/api/ask`.
- On `"win"` response: show a success message, disable input.
- On reaching 21 questions without a win: show "game over", no reveal.
- Minimal styling — functional, not fancy.

### 7. Deployment (`Dockerfile`, `pyproject.toml`)

`pyproject.toml` with dependencies: `fastapi`, `uvicorn[standard]`, `openai`.
Target Python 3.12+ (built-in `tomllib`).

`Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install .
COPY . .
CMD ["uvicorn", "src.h21.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Config and answers file bind-mounted or baked into the image.

## Implementation order

1. `config.toml` + `src/h21/config.py`
2. `src/h21/puzzle.py`
3. `src/h21/llm.py`
4. `src/h21/pow.py`
5. `src/h21/main.py`
6. `static/pow-worker.js`
7. `static/game.js` + `static/index.html` + `static/style.css`
8. `pyproject.toml` + `Dockerfile` + `.gitignore`

## Verification

- Run `uv run h21` locally with a `config.toml` and `daily-solutions.txt`.
- Open browser, verify the UI loads.
- Submit a question, verify PoW runs in the worker, question is answered.
- Verify the LLM response is one of the legal tokens.
- Verify 21-question limit works client-side.
- Verify `"win"` response triggers the win state.
