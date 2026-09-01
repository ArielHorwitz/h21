# Development

## Prerequisites

- Python 3.12+
- An OpenAI API key

## Local Setup

```bash
uv sync
```

Or with plain pip, install in editable mode (a non-editable install cannot
locate the repository's `static/` directory):

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Configuration

Config is loaded from `~/.config/h21/config.toml` with env var overrides. The data directory (database, logs, signing secret) defaults to `~/.local/share/h21/`.

**config.toml options:**

| Key | Env Override | Default | Description |
|-----|-------------|---------|-------------|
| `openai_api_key` | `OPENAI_API_KEY` | (required) | OpenAI API key |
| `model` | -- | `gpt-5.4-nano` | OpenAI model name |
| `reasoning_effort` | -- | `high` | Reasoning effort for the model |
| `secure_cookies` | -- | `false` | Mark session cookies HTTPS-only; enable behind TLS in deployment |
| `invite_request_hint` | -- | `Email` | Contact method shown on the login page for requesting an invite |
| `default_daily_question_limit` | -- | `200` | Default questions per account per day |
| `default_daily_topic_limit` | -- | `3` | Default topic suggestions per account per day |
| `avatar_image_model` | -- | `gpt-image-1-mini` | OpenAI model for avatar generation |
| `default_monthly_avatar_limit` | -- | `3` | Default avatar generations per month |
| `auto_generate_missing_avatars` | -- | `false` | Generate avatars automatically for accounts without one |

XDG base directories are respected. Override with `XDG_CONFIG_HOME` and `XDG_DATA_HOME`.

## Running

```bash
# Local development (localhost:8000)
OPENAI_API_KEY=sk-... h21

# Bind all interfaces on port 8000 (add a TLS proxy for public deployment)
h21 --public

# Custom host/port
h21 --host 0.0.0.0 --port 3000
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `h21` | Start the server |
| `h21-reset` | Confirm, then delete database, sessions, and logs while preserving avatars |
| `h21-invite` | Generate an invite code for user registration |
| `h21-sandbox` | Create and run a seeded local sandbox instance for testing |

## Local Testing Sandbox

`h21-sandbox` creates an isolated instance (default: `./.sandbox`, gitignored)
with its own XDG config and data directories, seeded with a `dev` account,
friend personas, friend connections, and fabricated play history — so the app
can be experienced as a normal user with active friends. The real database is
never touched.

```bash
# Create the sandbox and print the seeded accounts
h21-sandbox

# Create (or reuse) and start the server on it
h21-sandbox --serve

# Recreate from scratch with custom shape
h21-sandbox --force --friends 6 --days 14 --seed 42
```

All seeded accounts share one password (default: `sandbox`) and get real
AI-generated profile pictures from `assets/sandbox-avatars/` — samples
produced once by the in-game generator and committed to the repo, so seeding
itself makes no API calls (personas without a sample fall back to a locally
rendered identicon). Regenerate the samples with
`h21-sandbox --generate-samples` (uses the image API). Log in
as `dev`
(role `dev`) to see the app with friends, history, and suggestions populated;
the friend personas (`alice`, `bob`, ...) can be logged into as well. The
sandbox config copies the real `config.toml` (including the OpenAI key, with
`secure_cookies` and `auto_generate_missing_avatars` forced off), so playing
new games live works exactly like production. Seeded history is fabricated
locally — no API calls, deterministic under `--seed`.

## Project Structure

```
src/h21/          Backend Python source
static/           Frontend HTML, JS, CSS (served by FastAPI StaticFiles)
docs/             Project documentation
pyproject.toml    Dependencies and entry points
```
