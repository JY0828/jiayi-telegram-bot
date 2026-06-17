# jiayi-telegram-bot

Standalone Telegram Bot service and Telegram-only automation repository for Jiayi automations.

## Features

- Python Telegram Bot based on `python-telegram-bot`
- SQLite storage for chats and received messages
- `/start` to subscribe the current chat
- `/id` to show the current `TELEGRAM_CHAT_ID`
- `/status` to check active subscriptions
- `/stop` to disable the current chat
- Deutsch Telegram daily push via GitHub Actions

## Deutsch Telegram Automation

`.github/workflows/deutsch-telegram.yml` sends the Deutsch learning push to Telegram only.

Required repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional repository secret:

- `OPENAI_API_KEY`

Optional repository variable:

- `OPENAI_MODEL`, default `gpt-4.1-mini`

The scheduled workflow checks hourly and only sends during the 07:00 Europe/Berlin hour. It records successful daily sends in `sent_history.json` to avoid duplicates.

## Local Setup

1. Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Create a local `.env` file:

```powershell
Copy-Item .env.example .env
```

4. Edit `.env` and set:

```text
TELEGRAM_BOT_TOKEN=replace_me
SQLITE_DB_PATH=bot.db
```

5. Run the bot:

```powershell
python bot.py
```

6. Open your bot in Telegram and send:

```text
/start
/id
```

## Security

Do not commit real secrets or runtime files. This repository ignores:

- `.env`
- `*.db`
- `logs/`
- `__pycache__/`

If a Telegram token is ever exposed, revoke it with `@BotFather` and create a new token.
