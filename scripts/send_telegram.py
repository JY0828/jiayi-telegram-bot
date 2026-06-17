#!/usr/bin/env python3
"""Send Telegram HTML messages, splitting long content safely."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


MAX_MESSAGE = 3500


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def read_message() -> str:
    message_file = os.getenv("TELEGRAM_MESSAGE_FILE")
    if message_file:
        return Path(message_file).read_text(encoding="utf-8")
    return required("TELEGRAM_MESSAGE")


def split_message(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(block) > limit:
            cut = block.rfind("\n", 0, limit)
            if cut < limit // 2:
                cut = limit
            chunks.append(block[:cut].strip())
            block = block[cut:].strip()
        current = block
    if current:
        chunks.append(current)
    return chunks


def send_chunk(token: str, chat_id: str, text: str) -> None:
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API returned non-ok response: {data}")


def main() -> None:
    token = required("TELEGRAM_BOT_TOKEN")
    chat_id = required("TELEGRAM_CHAT_ID")
    message = read_message()
    chunks = split_message(message)
    for index, chunk in enumerate(chunks, start=1):
        prefix = f"<i>({index}/{len(chunks)})</i>\n\n" if len(chunks) > 1 else ""
        send_chunk(token, chat_id, prefix + chunk)
    print(f"Telegram sent chunks={len(chunks)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_line = f"{dt.datetime.now(dt.UTC).isoformat()} ERROR telegram_send_failed: {exc}\n"
        log_file = os.getenv("TELEGRAM_ERROR_LOG")
        if log_file:
            Path(log_file).write_text(log_line, encoding="utf-8")
        print(log_line, file=sys.stderr, end="")
        raise
