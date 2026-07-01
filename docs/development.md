# Development

## Prerequisites

- Python 3.12+
- An OpenAI API key

## Local Setup

```bash
python3 -m venv .venv
.venv/bin/pip install .
```

## Configuration

Config is loaded from `~/.config/h21/config.toml` with env var overrides. The data directory (database, logs, signing secret) defaults to `~/.local/share/h21/`.

**config.toml options:**

| Key | Env Override | Default | Description |
|-----|-------------|---------|-------------|
| `openai_api_key` | `OPENAI_API_KEY` | (required) | OpenAI API key |
| `model` | -- | `gpt-5.4-nano` | OpenAI model name |
| `reasoning_effort` | -- | `high` | Reasoning effort for the model |

XDG base directories are respected. Override with `XDG_CONFIG_HOME` and `XDG_DATA_HOME`.

## Running

```bash
# Local development (localhost:8000)
OPENAI_API_KEY=sk-... h21

# Public-facing (0.0.0.0:80)
h21 --public

# Custom host/port
h21 --host 0.0.0.0 --port 3000
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `h21` | Start the server |
| `h21-reset` | Delete the database and log files |
| `h21-invite` | Generate an invite code for user registration |

## Docker

```bash
docker build -t h21 .
docker run -e OPENAI_API_KEY=sk-... -p 8000:8000 h21
```

In Docker, config and data directories are `/app/config/h21/` and `/app/data/h21/`.

## Project Structure

```
src/h21/          Backend Python source
static/           Frontend HTML, JS, CSS (served by FastAPI StaticFiles)
docs/             Project documentation
pyproject.toml    Dependencies and entry points
Dockerfile        Container definition
```
