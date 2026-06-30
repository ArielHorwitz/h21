# Ubuntu VPS Setup

Minimal deployment of h21 on an Ubuntu VPS. No domain name, no TLS — accessed
directly by IP address. The app runs in a `screen` session rather than as a
systemd service.

## Prerequisites

- Ubuntu VPS with SSH access
- OpenAI API key

## 1. Install uv and system tools

```bash
apt update && apt upgrade -y
apt install -y git screen
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 2. Clone and sync

```bash
git clone <repo-url> /opt/h21
cd /opt/h21
uv sync
```

`uv sync` installs the pinned Python version (from `.python-version`),
creates the virtualenv, and installs all locked dependencies.

## 3. Configure

```bash
mkdir -p /opt/h21/config/h21 /opt/h21/data/h21
```

Create `/opt/h21/config/h21/config.toml`:

```toml
pow_difficulty = 20
# bypass_password = "optional-password"
```

## 4. Run

```bash
screen -S h21
cd /opt/h21
OPENAI_API_KEY=sk-... \
XDG_CONFIG_HOME=/opt/h21/config \
XDG_DATA_HOME=/opt/h21/data \
uv run h21 --public
```

Detach with `Ctrl+A` then `D`. Reattach with `screen -r h21`.

## 5. Firewall

If using `ufw`:

```bash
ufw allow 8000/tcp
```

## 6. Access

Open `http://<vps-ip>:8000` in a browser.

## Updating

```bash
screen -r h21
# Ctrl+C to stop
cd /opt/h21
git pull
uv sync
OPENAI_API_KEY=sk-... \
XDG_CONFIG_HOME=/opt/h21/config \
XDG_DATA_HOME=/opt/h21/data \
uv run h21 --public
```

## Resetting state

If the database schema has changed and you need a fresh start:

```bash
XDG_DATA_HOME=/opt/h21/data uv run h21-reset
```

This deletes the database and log files from the data directory.

## Checking logs

Uvicorn logs directly to the screen session. Reattach with `screen -r h21`.
Log files are also written to the data directory (`/opt/h21/data/h21/`).
