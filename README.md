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

`.github/workflows/deutsch-telegram.yml` sends Deutsch Reaktivierung v5 to Telegram only.

Required repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional repository secret:

- `OPENAI_API_KEY`

Optional repository variable:

- `OPENAI_MODEL`, default `gpt-4.1-mini`

The scheduled workflow uses several non-top-of-hour attempts during the 07:00-08:59 Europe/Berlin window. It records successful daily sends in `sent_history.json` to avoid duplicates, so at most one Telegram push is sent per day.

The v5 format uses a light push plus a detail page. Telegram receives only the scenario title, listening title, news title, three takeaways, and a link to the full static HTML page. The detail page is generated under `outputs/deutsch-pages/YYYY-MM-DD.html` and deployed with GitHub Pages.

The detail page is a German-life reading assistant: Chinese-first explanations, full life-scenario dialogue, reusable German sentences, short listening guidance, German-news body extraction when available, dynamic key vocabulary, high-frequency expressions, and three takeaways for the day. When article body or video transcript extraction fails, the page says so explicitly instead of inventing full translations or fake key sentences.

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
