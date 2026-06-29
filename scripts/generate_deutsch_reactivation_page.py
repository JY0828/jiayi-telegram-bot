#!/usr/bin/env python3
"""Generate Deutsch Reaktivierung v5: short push plus a static detail page."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import generate_deutsch_reactivation_email as base


DEFAULT_PAGE_BASE = "https://htmlpreview.github.io/?https://github.com/JY0828/jiayi-telegram-bot/blob/main/outputs"
DW_SLOW_NEWS_URL = "https://learngerman.dw.com/de/langsam-gesprochene-nachrichten/s-60040332"
DW_TOPTHEMA_FEED = "https://rss.dw.com/xml/dkpodcast_topthemamitvokabeln_de"
NACHRICHTENLEICHT_FEED = "https://www.deutschlandfunk.de/podcast-nachrichtenleicht-der-wochenrueckblick-in-einfacher-sprache-100.xml"
LIFE_DIALOGUE_CANDIDATES = (
    {
        "source": "lingoneo",
        "url": "https://www.lingoneo.org/learn-german/page/learn-essential-phrases/daily-life/a-doctors-appointment/page-1756",
        "theme": "Arztpraxis: Anmeldung am Empfang",
        "topic": "在 Arztpraxis 前台说明来意和确认预约",
        "intro": "在德国看家庭医生、Kinderarzt 或专科医生时，第一关通常是前台 Anmeldung。这个场景练的是：说明自己有预约、说明来看哪位医生、填写病史表，以及听懂“请坐、医生马上来”。",
        "verify_phrases": ("Haben Sie einen Termin?", "Ich habe einen Termin um 14 Uhr.", "Der Arzt wird in Kürze bei Ihnen sein."),
        "dialogue": [
            ("Empfang", "Guten Morgen, wie kann ich Ihnen heute helfen?", "早上好，今天有什么可以帮您的？"),
            ("Patientin", "Ich möchte einen Arzt sprechen.", "我想见医生。"),
            ("Empfang", "Haben Sie einen Termin?", "您有预约吗？"),
            ("Patientin", "Ja, ich habe einen Termin um 14 Uhr.", "有的，我预约的是14点。"),
            ("Empfang", "Sind Sie hier, um Dr. Fiedler zu sehen?", "您是来看 Fiedler 医生的吗？"),
            ("Patientin", "Ja, genau. Ich bin hier, um Dr. Fiedler zu sehen.", "是的，没错。我是来看 Fiedler 医生的。"),
            ("Empfang", "Könnten Sie bitte Ihre medizinische Vorgeschichte auf diesem Formular eintragen?", "您能在这张表上填写一下您的既往病史吗？"),
            ("Patientin", "Ja, natürlich. Wo soll ich das Formular danach abgeben?", "当然可以。填完以后我应该把表交到哪里？"),
            ("Empfang", "Bitte geben Sie es wieder an der Anmeldung ab. Der Arzt wird in Kürze bei Ihnen sein.", "请把它交回前台。医生很快就会来。"),
        ],
        "useful": [
            ("Ich habe einen Termin um 14 Uhr.", "我预约的是14点。", "医生前台、Kinderradiologie、Bürgerbüro、Kita Gesprächstermin"),
            ("Ich bin hier, um Dr. Fiedler zu sehen.", "我是来看 Fiedler 医生的。", "到诊所/医院前台报到"),
            ("Könnten Sie bitte kurz prüfen, ob ich richtig bin?", "您能帮我确认一下我是不是来对地方了吗？", "医院、Radiologie、大楼内找科室"),
            ("Wo soll ich das Formular danach abgeben?", "填完以后我应该把表交到哪里？", "诊所、保险、行政窗口"),
            ("Der Arzt wird in Kürze bei Ihnen sein.", "医生很快就会来。", "听懂前台说明"),
        ],
        "substitution": [
            {
                "pattern": "Ich habe einen Termin um ...",
                "items": ["um 8:30 Uhr", "beim Kinderarzt", "bei der Radiologie", "bei der Ausländerbehörde"],
            },
            {
                "pattern": "Ich bin hier, um ... zu sehen.",
                "items": ["Dr. Fiedler", "die Kinderärztin", "die Sachbearbeiterin", "Herrn Müller von der Versicherung"],
            },
        ],
        "history_topics": ("Arztpraxis Anmeldung", "Kinderarzt", "Kinderradiologie"),
    },
    {
        "source": "lingoneo",
        "url": "https://www.lingoneo.org/learn-german/page/learn-essential-phrases/daily-life/a-dentist-appointment/page-1755",
        "theme": "Zahnarztpraxis: Schmerzen schildern",
        "topic": "在牙医前台/问诊时说明疼痛情况",
        "intro": "在德国看牙医或带孩子去牙科时，经常需要先简单说明疼痛程度和开始时间。这个场景练的是：自然回答 Wie geht es Ihnen?、说明疼痛、回答症状开始时间。",
        "verify_phrases": ("Mein Zahn tut sehr weh.", "Wann haben die Zahnschmerzen denn angefangen?"),
        "dialogue": [
            ("Zahnarzt", "Guten Morgen. Wie geht es Ihnen heute?", "早上好。您今天感觉怎么样？"),
            ("Patient", "Es geht so. Mein Zahn tut sehr weh.", "还行吧。我的牙很疼。"),
            ("Zahnarzt", "Wann haben die Zahnschmerzen denn angefangen?", "牙痛是什么时候开始的？"),
            ("Patient", "Gestern Abend. Seitdem ist es schlimmer geworden.", "昨天晚上。从那以后越来越严重了。"),
            ("Zahnarzt", "Tut es die ganze Zeit weh oder nur beim Kauen?", "是一直疼，还是只有咀嚼时疼？"),
            ("Patient", "Vor allem beim Kauen und wenn ich etwas Kaltes trinke.", "主要是咀嚼时，还有喝冷饮时。"),
            ("Zahnarzt", "Dann schauen wir uns das gleich an.", "那我们马上检查一下。"),
        ],
        "useful": [
            ("Es geht so. Mein Zahn tut sehr weh.", "还行吧。我的牙很疼。", "牙医、Kinderarzt 描述疼痛"),
            ("Seit gestern Abend ist es schlimmer geworden.", "从昨天晚上开始变严重了。", "描述病情变化"),
            ("Tut es die ganze Zeit weh oder nur beim Kauen?", "是一直疼，还是只有咀嚼时疼？", "听懂医生追问"),
            ("Vor allem beim Kauen.", "主要是咀嚼时。", "回答症状触发条件"),
            ("Dann schauen wir uns das gleich an.", "那我们马上看一下。", "听懂医生安排"),
        ],
        "substitution": [
            {
                "pattern": "Seit ... ist es schlimmer geworden.",
                "items": ["seit gestern Abend", "seit heute Morgen", "seit dem Wochenende", "seit der Impfung"],
            },
            {
                "pattern": "Vor allem bei/beim ...",
                "items": ["beim Kauen", "beim Schlucken", "beim Laufen", "bei kalten Getränken"],
            },
        ],
        "history_topics": ("Zahnarzt", "Schmerzen schildern"),
    },
    {
        "source": "lingoneo",
        "url": "https://www.lingoneo.org/learn-german/page/learn-essential-phrases/business/telephoning/page-1797",
        "theme": "Telefon: jemanden erreichen oder Rückruf erbitten",
        "topic": "电话里找人、留言并请求回电",
        "intro": "在德国打电话给诊所、Kita、保险公司或 Hausverwaltung 时，经常需要说明自己是谁、想找谁、对方不在时请求回电。这个场景练的是最常用的电话开场和留言。",
        "verify_phrases": ("Hier spricht", "Ist Lisa zu sprechen?", "Wer spricht?"),
        "dialogue": [
            ("Anruferin", "Guten Tag, hier spricht Li Wang.", "您好，我是 Li Wang。"),
            ("Empfang", "Guten Tag. Worum geht es?", "您好。请问是什么事？"),
            ("Anruferin", "Ist Frau Schneider zu sprechen?", "Schneider 女士在吗？"),
            ("Empfang", "Einen Moment bitte. Nein, sie ist gerade nicht am Platz.", "请稍等。不，她现在不在座位上。"),
            ("Anruferin", "Könnten Sie ihr bitte ausrichten, dass ich angerufen habe?", "您能帮我转告她我来过电话吗？"),
            ("Empfang", "Natürlich. Worum geht es genau?", "当然。具体是什么事？"),
            ("Anruferin", "Es geht um unseren Termin am Freitag. Ich hätte dazu noch eine Rückfrage.", "是关于我们周五的预约。我还有一个问题想确认。"),
            ("Empfang", "Soll Frau Schneider Sie zurückrufen?", "需要 Schneider 女士给您回电话吗？"),
            ("Anruferin", "Ja, bitte. Am besten unter dieser Nummer.", "是的，麻烦了。最好打这个号码。"),
        ],
        "useful": [
            ("Guten Tag, hier spricht Li Wang.", "您好，我是 Li Wang。", "任何正式电话开场"),
            ("Ist Frau Schneider zu sprechen?", "Schneider 女士在吗？", "诊所、Kita、保险、Hausverwaltung"),
            ("Könnten Sie ihr bitte ausrichten, dass ich angerufen habe?", "您能转告她我来过电话吗？", "留言"),
            ("Es geht um unseren Termin am Freitag.", "是关于我们周五的预约。", "说明来电事项"),
            ("Könnte sie mich bitte zurückrufen?", "她能给我回个电话吗？", "请求回电"),
        ],
        "substitution": [
            {
                "pattern": "Es geht um ...",
                "items": ["unseren Termin", "die Rechnung", "die Kita-Anmeldung", "meinen Vertrag"],
            },
            {
                "pattern": "Könnten Sie bitte ausrichten, dass ...",
                "items": ["ich angerufen habe", "ich den Termin verschieben muss", "ich noch Unterlagen brauche"],
            },
        ],
        "history_topics": ("Telefon Rückruf", "Mailbox", "Termin Rückfrage"),
    },
)


class ParagraphExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._stack: list[str] = []
        self._buf: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "footer", "header", "aside"}:
            self._stack.append(tag)
            return
        if tag in {"p", "li", "h1", "h2", "h3", "tkds-text", "tkds-headline"}:
            self._stack.append(tag)
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        if self._stack[-1] == tag:
            if tag in {"p", "li", "h1", "h2", "h3", "tkds-text", "tkds-headline"}:
                text = base.clean_text(" ".join(self._buf))
                if is_content_paragraph(text):
                    self.paragraphs.append(text)
                self._buf = []
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if not self._stack:
            return
        if self._stack[-1] in {"script", "style", "nav", "footer", "header", "aside"}:
            return
        if self._stack[-1] in {"p", "li", "h1", "h2", "h3", "tkds-text", "tkds-headline"}:
            self._buf.append(data)


def h(text: str) -> str:
    return html.escape(text or "", quote=True)


def tg(text: str) -> str:
    return html.escape(text or "", quote=False)


def is_content_paragraph(text: str) -> bool:
    if len(text) < 45:
        return False
    lowered = text.casefold()
    noisy = (
        "hauptnavigation",
        "nebennavigation",
        "untermenü",
        "pfeil rechts",
        "close menu",
        "newsletter",
        "teilen",
        "download",
        "audio",
        "video",
        "matomo",
        "einwilligung",
        "webverhalten",
        "datenschutz",
        "cookie",
        "sprachauswahl",
        "english",
        "icon",
        "kontakt",
        "barrierefreiheit",
    )
    return sum(marker in lowered for marker in noisy) == 0


def fetch_raw(url: str) -> tuple[str, str | None]:
    try:
        return base.fetch_text(url, timeout=25), None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=25, context=ssl._create_unverified_context()) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace"), None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return "", str(exc)


def absolute_url(url: str, base_url: str) -> str:
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        if "learngerman.dw.com" in base_url:
            return "https://learngerman.dw.com" + url
        return "https://www.deutschlandfunk.de" + url
    return url


def apollo_state(raw: str) -> dict:
    match = re.search(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\});", raw, re.S)
    if not match:
        return {}
    return json.loads(match.group(1))


def html_to_paragraphs(fragment: str) -> list[str]:
    parser = ParagraphExtractor()
    parser.feed(fragment)
    paragraphs = []
    for text in parser.paragraphs:
        text = base.clean_text(text)
        if text and text not in paragraphs:
            paragraphs.append(text)
    return paragraphs


def html_to_sections(fragment: str) -> list[dict]:
    parts = re.split(r"(?is)<h2[^>]*>(.*?)</h2>", fragment)
    sections: list[dict] = []
    if parts and base.clean_text(re.sub(r"<[^>]+>", " ", parts[0])):
        sections.append({"heading": "", "paragraphs": html_to_paragraphs(parts[0])})
    for i in range(1, len(parts), 2):
        heading = base.clean_text(re.sub(r"<[^>]+>", " ", parts[i]))
        body = parts[i + 1] if i + 1 < len(parts) else ""
        paragraphs = html_to_paragraphs(body)
        if heading or paragraphs:
            sections.append({"heading": heading, "paragraphs": paragraphs})
    return [s for s in sections if s["heading"] or s["paragraphs"]]


def manuscript_to_paragraphs(fragment: str) -> list[str]:
    fragment = re.sub(r"(?i)<br\s*/?>", "</p><p>", fragment)
    paragraphs = html_to_paragraphs(fragment)
    cleaned: list[str] = []
    for paragraph in paragraphs:
        paragraph = re.sub(r"^\s*[\wÄÖÜäöüß -]+?\s+–\s+", "", paragraph).strip()
        if paragraph and paragraph not in cleaned:
            cleaned.append(paragraph)
    return cleaned


def article_text_length(sections: list[dict]) -> int:
    return sum(len(p) for section in sections for p in section["paragraphs"])


def quality_ok(sections: list[dict], minimum_chars: int) -> bool:
    text = " ".join(p for section in sections for p in section["paragraphs"]).casefold()
    if len(text) < minimum_chars:
        return False
    bad = sum(text.count(word) for word in ("beschreibung", "description", "overview", "zusammenfassung", "abstract"))
    return bad <= 2


def dw_article_from_url(url: str) -> dict | None:
    raw, error = fetch_raw(url)
    if error:
        return None
    state = apollo_state(raw)
    articles = [v for v in state.values() if isinstance(v, dict) and v.get("__typename") == "Article"]
    article = max(articles, key=lambda item: len(item.get("text") or ""), default=None)
    if not article or not article.get("text"):
        return None
    sections = html_to_sections(article["text"])
    mp3 = ""
    for value in state.values():
        if isinstance(value, dict) and value.get("__typename") == "Audio" and value.get("mp3Src"):
            mp3 = value["mp3Src"]
            break
    return {
        "source": "DW Learn German",
        "title": article.get("name") or article.get("shortTitle") or "DW Learn German",
        "url": absolute_url(article.get("namedUrl") or url, "https://learngerman.dw.com"),
        "sections": sections,
        "audio_url": mp3,
    }


def dw_lesson_from_url(url: str) -> dict | None:
    raw, error = fetch_raw(url)
    if error:
        return None
    state = apollo_state(raw)
    lessons = [v for v in state.values() if isinstance(v, dict) and v.get("__typename") == "Lesson"]
    lesson = max(lessons, key=lambda item: len(item.get("manuscript") or ""), default=None)
    if not lesson or not lesson.get("manuscript"):
        return None
    paragraphs = manuscript_to_paragraphs(lesson["manuscript"])
    if len(paragraphs) < 4:
        return None
    return {
        "source": "DW Top-Thema mit Vokabeln",
        "title": lesson.get("name") or "DW Top-Thema",
        "url": absolute_url(lesson.get("canonicalUrl") or lesson.get("namedUrl") or url, "https://learngerman.dw.com"),
        "sections": [{"heading": lesson.get("name") or "DW Top-Thema", "paragraphs": paragraphs}],
        "audio_url": "",
    }


def dw_slow_news_candidates(limit: int = 12) -> list[str]:
    raw, error = fetch_raw(DW_SLOW_NEWS_URL)
    if error:
        return []
    urls: list[str] = []
    for match in re.finditer(r'href="([^"]+/de/[^"]+langsam-gesprochene-nachrichten/a-\d+)"', raw):
        url = absolute_url(match.group(1), DW_SLOW_NEWS_URL)
        if url not in urls:
            urls.append(url)
    for match in re.finditer(r'href="(/de/[^"]+langsam-gesprochene-nachrichten/a-\d+)"', raw):
        url = absolute_url(match.group(1), DW_SLOW_NEWS_URL)
        if url not in urls:
            urls.append(url)
    return urls[:limit]


def recent_values(history: list[dict], key: str, limit: int = 10) -> set[str]:
    return {
        str(entry.get(key, "")).casefold()
        for entry in history[-limit:]
        if entry.get(key)
    }


def choose_dw_slow_news(
    minimum_chars: int,
    require_audio: bool,
    skip_url: str | None = None,
    history: list[dict] | None = None,
    history_keys: tuple[str, ...] = ("listening_link", "news_link"),
) -> dict:
    recently_used: set[str] = set()
    if history:
        for key in history_keys:
            recently_used.update(recent_values(history, key, limit=14))
    articles: list[dict] = []
    for url in dw_slow_news_candidates():
        if skip_url and url == skip_url:
            continue
        article = dw_article_from_url(url)
        if not article:
            continue
        if require_audio and not article["audio_url"]:
            continue
        if quality_ok(article["sections"], minimum_chars):
            articles.append(article)
    if articles:
        articles.sort(key=lambda item: article_date_key(item.get("title", "")), reverse=True)
        unused = [item for item in articles if item["url"].casefold() not in recently_used]
        if not unused:
            return articles[0]
        newest = article_date_key(articles[0].get("title", ""))
        freshest_unused = article_date_key(unused[0].get("title", ""))
        if date_distance_days(newest, freshest_unused) <= 2:
            return unused[0]
        return articles[0]
    raise RuntimeError("No complete DW slow-news article passed quality checks.")


def nachrichtenleicht_candidates(limit: int = 8) -> list[str]:
    try:
        import xml.etree.ElementTree as ET

        raw = base.fetch_text(NACHRICHTENLEICHT_FEED)
        root = ET.fromstring(raw)
    except Exception:
        return []
    urls = []
    for item in root.findall(".//item")[:limit]:
        link = item.findtext("link") or ""
        if link and link not in urls:
            urls.append(link)
    return urls


def dw_topthema_candidates(limit: int = 8) -> list[str]:
    try:
        import xml.etree.ElementTree as ET

        raw = base.fetch_text(DW_TOPTHEMA_FEED)
        root = ET.fromstring(raw)
    except Exception:
        return []
    urls: list[str] = []
    for item in root.findall(".//item")[:limit]:
        link = item.findtext("link") or ""
        if link and link not in urls:
            urls.append(link)
    return urls


def deutschlandfunk_teaser_article(url: str) -> dict | None:
    raw, error = fetch_raw(url)
    if error:
        return None
    parser = ParagraphExtractor()
    parser.feed(raw)
    paragraphs = [p for p in parser.paragraphs if "Nachrichtenleicht" not in p and "Podcast" not in p]
    paragraphs = [p for p in paragraphs if len(p) > 80]
    if len(paragraphs) < 4:
        return None
    sections = [{"heading": "Nachrichtenleicht", "paragraphs": paragraphs[:10]}]
    return {"source": "Nachrichtenleicht", "title": paragraphs[0][:80], "url": url, "sections": sections, "audio_url": ""}


def choose_reading_article(
    preferred: dict | None = None,
    skip_url: str | None = None,
    history: list[dict] | None = None,
) -> dict:
    recent_news = recent_values(history or [], "news_link", limit=14)
    if (
        preferred
        and not skip_url
        and preferred["url"].casefold() not in recent_news
        and quality_ok(preferred["sections"], 500)
    ):
        return {**preferred, "audio_url": ""}
    for url in dw_topthema_candidates():
        if skip_url and url == skip_url:
            continue
        if url.casefold() in recent_news:
            continue
        article = dw_lesson_from_url(url)
        if article and quality_ok(article["sections"], 500):
            return article
    for url in dw_topthema_candidates():
        if skip_url and url == skip_url:
            continue
        article = dw_lesson_from_url(url)
        if article and quality_ok(article["sections"], 500):
            return article
    # Nachrichtenleicht is intentionally probed but not accepted here yet: the current
    # pages often mix teaser text with Deutschlandfunk navigation/topic blocks. That is
    # worse than switching sources, so use the full-text DW fallback.
    _ = nachrichtenleicht_candidates()
    articles: list[dict] = []
    for url in dw_slow_news_candidates():
        if skip_url and url == skip_url:
            continue
        article = dw_article_from_url(url)
        if article and quality_ok(article["sections"], 500):
            articles.append(article)
    if not articles:
        raise RuntimeError("No complete reading article passed quality checks.")
    articles.sort(key=lambda item: article_date_key(item.get("title", "")), reverse=True)
    unused = [item for item in articles if item["url"].casefold() not in recent_news]
    if not unused:
        return articles[0]
    newest = article_date_key(articles[0].get("title", ""))
    freshest_unused = article_date_key(unused[0].get("title", ""))
    if date_distance_days(newest, freshest_unused) <= 2:
        return unused[0]
    return articles[0]


def article_date_key(title: str) -> tuple[int, int, int]:
    match = re.search(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", title or "")
    if not match:
        return (0, 0, 0)
    day, month, year = (int(part) for part in match.groups())
    return (year, month, day)


def date_distance_days(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    if 0 in left or 0 in right:
        return 999
    try:
        import datetime as dt

        return abs((dt.date(*left) - dt.date(*right)).days)
    except ValueError:
        return 999


def life_matches_history(entry: dict, candidate: dict) -> bool:
    values = {
        str(entry.get("life_url", "")).casefold(),
        str(entry.get("life_topic", "")).casefold(),
        str(entry.get("topic", "")).casefold(),
    }
    if candidate["url"].casefold() in values:
        return True
    return any(topic.casefold() in values for topic in candidate.get("history_topics", ()))


def ordered_life_candidates(history: list[dict]) -> list[dict]:
    scored: list[tuple[int, int, dict]] = []
    for index, candidate in enumerate(LIFE_SOURCE_CANDIDATES):
        last_seen = -1
        for pos, entry in enumerate(history):
            if life_matches_history(entry, candidate):
                last_seen = pos
        scored.append((last_seen, index, candidate))
    return [candidate for _last_seen, _index, candidate in sorted(scored, key=lambda item: (item[0] != -1, item[0], item[1]))]


def life_usage_count(history: list[dict], candidate: dict) -> int:
    return sum(1 for entry in history if life_matches_history(entry, candidate))


def rotate_paragraph_slice(paragraphs: list[str], usage_count: int, size: int = 8) -> tuple[list[str], int]:
    if len(paragraphs) <= size:
        return paragraphs, 0
    max_start = len(paragraphs) - size
    start = (usage_count * 4) % (max_start + 1)
    return paragraphs[start : start + size], start


def dialogue_page_ok(candidate: dict) -> bool:
    raw, error = fetch_raw(candidate["url"])
    if error:
        return False
    lowered = base.clean_text(raw).casefold()
    if "practice dialogue" not in lowered and "phrases" not in lowered and "dialogue" not in lowered:
        return False
    return any(phrase.casefold() in lowered for phrase in candidate.get("verify_phrases", ()))


def dialogue_to_paragraphs(dialogue: list[tuple[str, str, str]]) -> list[str]:
    return [f"{speaker}: {de}" for speaker, de, _cn in dialogue]


def ordered_life_dialogues(history: list[dict]) -> list[dict]:
    recent = history[-30:]
    scored: list[tuple[int, int, dict]] = []
    for index, candidate in enumerate(LIFE_DIALOGUE_CANDIDATES):
        last_seen = -1
        for pos, entry in enumerate(recent):
            if life_matches_history(entry, candidate):
                last_seen = pos
        scored.append((last_seen, index, candidate))
    return [candidate for _last_seen, _index, candidate in sorted(scored, key=lambda item: (item[0] != -1, item[0], item[1]))]


def choose_life_article(history: list[dict]) -> dict:
    raw_index = os.getenv("DEUTSCH_LIFE_INDEX", "").strip()
    ordered = ordered_life_dialogues(history)
    if raw_index.isdigit():
        ordered = list(LIFE_DIALOGUE_CANDIDATES)
        index = int(raw_index) % len(ordered)
        ordered = ordered[index:] + ordered[:index]
    for candidate in ordered:
        if not dialogue_page_ok(candidate):
            continue
        paragraphs = dialogue_to_paragraphs(candidate["dialogue"])
        return {
            **candidate,
            "paragraphs": paragraphs,
            "slice_start": 0,
            "sections": [{"heading": candidate["theme"], "paragraphs": paragraphs}],
        }
    raise RuntimeError("No verified dialogue source passed quality checks.")


def relevant_life_paragraphs(paragraphs: list[str], keywords: tuple[str, ...]) -> list[str]:
    scored = []
    for paragraph in paragraphs:
        lower = paragraph.casefold()
        score = sum(1 for keyword in keywords if keyword in lower)
        scored.append((score, paragraph))
    start = next((idx for idx, (score, _) in enumerate(scored) if score > 0), 0)
    selected: list[str] = []
    misses = 0
    for score, paragraph in scored[start:]:
        if score > 0 or len(selected) < 3:
            selected.append(paragraph)
            misses = 0 if score > 0 else misses + 1
        else:
            misses += 1
            if misses <= 1 and len(paragraph.split()) >= 10:
                selected.append(paragraph)
        if len(selected) >= 10:
            break
        if len(selected) >= 5 and misses >= 2:
            break
    return selected or paragraphs


def choose_scenario_for_life(life: dict, history: list[dict], weekend: bool = False) -> dict:
    haystack = f"{life.get('theme', '')} {life.get('topic', '')} {life.get('url', '')}".casefold()
    preferred_topic = ""
    if "fieber" in haystack or "kinderarzt" in haystack:
        preferred_topic = "Kinderarzt"
    elif "116117" in haystack or "facharzt" in haystack:
        preferred_topic = "116117 / Facharzttermin"
    elif "kita" in haystack:
        preferred_topic = "Kita / Eingewöhnung"
    elif "bürgeramt" in haystack:
        preferred_topic = "Bürgeramt"
    elif "elterngeld" in haystack or "antrag" in haystack:
        preferred_topic = "Bürgeramt"
    if preferred_topic:
        for scenario in base.SCENARIOS:
            if scenario.get("topic") == preferred_topic:
                return scenario
    return base.choose_scenario(history, weekend=weekend)


def extract_escaped_field(raw: str, field: str) -> str:
    match = re.search(rf"&quot;{re.escape(field)}&quot;:&quot;(.*?)&quot;", raw)
    if not match:
        match = re.search(rf'"{re.escape(field)}"\s*:\s*"(.*?)"', raw)
    if not match:
        return ""
    value = html.unescape(match.group(1))
    if "\\u" in value:
        value = value.encode("utf-8", errors="ignore").decode("unicode_escape", errors="ignore")
    return base.clean_text(value)


def relevance_keywords(item: base.MediaItem) -> set[str]:
    raw = f"{item.title} {item.summary}"
    words = re.findall(r"[A-Za-zÄÖÜäöüß-]{6,}", raw)
    stop = {
        "deutschland",
        "deutschlandfunk",
        "aktuelle",
        "beiträge",
        "nachrichten",
        "hintergründe",
        "schwerpunkt",
    }
    return {word.casefold().strip("-") for word in words if word.casefold() not in stop}


def filter_relevant_paragraphs(paragraphs: list[str], item: base.MediaItem | None) -> list[str]:
    if item is None:
        return paragraphs
    keywords = relevance_keywords(item)
    if not keywords:
        return paragraphs
    scored: list[tuple[int, str]] = []
    for paragraph in paragraphs:
        lower = paragraph.casefold()
        score = sum(1 for keyword in keywords if keyword in lower)
        scored.append((score, paragraph))
    if sum(1 for score, _ in scored if score > 0) < 2:
        return paragraphs

    selected: list[str] = []
    started = False
    misses_after_start = 0
    for score, paragraph in scored:
        if score > 0:
            started = True
            misses_after_start = 0
            selected.append(paragraph)
            continue
        if not started:
            continue
        misses_after_start += 1
        if misses_after_start <= 1 and len(paragraph.split()) >= 12:
            selected.append(paragraph)
        if misses_after_start >= 2:
            break
    return selected or paragraphs


def extract_article_paragraphs(url: str, item: base.MediaItem | None = None) -> tuple[list[str], str | None]:
    raw, error = fetch_raw(url)
    if error:
        return [], error
    parser = ParagraphExtractor()
    parser.feed(raw)
    paragraphs: list[str] = []
    seen: set[str] = set()
    for text in parser.paragraphs:
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        paragraphs.append(text)
    paragraphs = filter_relevant_paragraphs(paragraphs, item)
    if len(paragraphs) < 2 or sum(len(p.split()) for p in paragraphs) < 60:
        teaser = extract_escaped_field(raw, "teasertext") or extract_escaped_field(raw, "seoTeaserText")
        if teaser:
            return [teaser], "只抓到结构化简介，未抓到完整正文段落。"
        return [], "正文段落不足，可能只抓到了页面导航、标题或简介。"
    return paragraphs[:24], None


def translate_paragraphs(paragraphs: list[str]) -> tuple[list[str], str | None]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not paragraphs:
        return [], "没有可翻译的正文段落。"
    if not api_key:
        return translate_paragraphs_public(paragraphs)
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    prompt = (
        "请把下面德语新闻正文逐段翻译成自然中文。要求保留段落顺序，不总结，不扩写。"
        "返回 JSON 数组，数组长度必须等于输入段落数，每项只包含中文译文。\n\n"
        + json.dumps(paragraphs, ensure_ascii=False)
    )
    payload = json.dumps(
        {
            "model": model,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return translate_paragraphs_public(paragraphs)
    text = data.get("output_text", "")
    if not text:
        chunks: list[str] = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    chunks.append(content["text"])
        text = "\n".join(chunks)
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        translated = json.loads(text)
    except json.JSONDecodeError:
        translated = [line.strip() for line in text.splitlines() if line.strip()]
    if not isinstance(translated, list) or len(translated) != len(paragraphs):
        return translate_paragraphs_public(paragraphs)
    return [str(item).strip() for item in translated], None


def translate_one_public(text: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "de",
            "tl": "zh-CN",
            "dt": "t",
            "q": text,
        }
    )
    request = urllib.request.Request(
        f"https://translate.googleapis.com/translate_a/single?{query}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    return "".join(part[0] for part in data[0] if part and part[0]).strip()


def translate_paragraphs_public(paragraphs: list[str]) -> tuple[list[str], str | None]:
    translated: list[str] = []
    try:
        for paragraph in paragraphs:
            translated.append(translate_one_public(paragraph))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError, IndexError, TypeError) as exc:
        return [], f"public translation fallback failed: {exc}"
    if len(translated) != len(paragraphs) or any(not item for item in translated):
        return [], "public translation fallback returned incomplete output"
    return translated, None


def translate_required(paragraphs: list[str], label: str) -> list[str]:
    translated, error = translate_paragraphs(paragraphs)
    if error or not translated:
        raise RuntimeError(f"{label} translation failed: {error or 'empty translation'}")
    return translated


def translate_best_effort(paragraphs: list[str], label: str) -> list[str]:
    translated, error = translate_paragraphs(paragraphs)
    if error or len(translated) != len(paragraphs):
        print(f"WARN optional_translation_failed label={label} error={error}", file=sys.stderr)
        return ["" for _ in paragraphs]
    return translated


def openai_brief_summary(title: str, text: str, label: str) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    prompt = (
        f"请根据下面德语正文，用中文概括“{label}”的真实内容。"
        "要求：只写一句话，45-70个中文字符；必须说清发生了什么/讨论什么；"
        "不要只复述标题，不要写学习建议，不要扩写背景。\n\n"
        f"标题：{title}\n\n正文：{text[:5000]}"
    )
    payload = json.dumps(
        {
            "model": model,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return None
    summary = data.get("output_text", "").strip()
    if not summary:
        chunks: list[str] = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    chunks.append(content["text"])
        summary = " ".join(chunks).strip()
    summary = re.sub(r"^[\"“]|[\"”]$", "", summary.strip())
    return summary or None


def fallback_brief_summary(translated: list[str], title: str) -> str:
    for paragraph in translated:
        text = base.clean_text(paragraph)
        if len(text) >= 25:
            sentence = re.split(r"(?<=[。！？；])", text)[0].strip()
            if len(sentence) < 25:
                sentence = text
            return sentence[:68].rstrip("，。；、 ") + "。"
    return f"本模块围绕 {title} 的正文内容展开。"


def flatten_sections(sections: list[dict]) -> list[str]:
    paragraphs: list[str] = []
    for section in sections:
        if section.get("heading"):
            paragraphs.append(section["heading"])
        paragraphs.extend(section.get("paragraphs", []))
    return paragraphs


def sections_html(sections: list[dict]) -> str:
    chunks = []
    for section in sections:
        if section.get("heading"):
            chunks.append(f"<h3>{h(section['heading'])}</h3>")
        for paragraph in section.get("paragraphs", []):
            chunks.append(f"<p>{h(paragraph)}</p>")
    return "".join(chunks)


def translated_html(original: list[str], translated: list[str]) -> str:
    chunks = []
    for source, zh in zip(original, translated):
        if len(source) < 95 and not source.endswith("."):
            chunks.append(f"<h3>{h(zh)}</h3>")
        else:
            chunks.append(f"<p>{h(zh)}</p>")
    return "".join(chunks)


def life_dialogue_html(dialogue: list[tuple[str, str, str]]) -> str:
    return "".join(
        f"<div class='item'><b>{h(speaker)}:</b> {h(de)}</div>"
        for speaker, de, _cn in dialogue
    )


def life_dialogue_translation_html(dialogue: list[tuple[str, str, str]]) -> str:
    return "".join(
        f"<div class='item'><b>{h(speaker)}:</b> {h(cn)}</div>"
        for speaker, _de, cn in dialogue
    )


def useful_sentence_html(rows: list[tuple[str, str, str]]) -> str:
    return "".join(
        f"<div class='item'><b>德语：</b> {h(de)}<br><b>中文：</b> {h(cn)}<br><b>适用场景：</b> {h(scene)}</div>"
        for de, cn, scene in rows
    )


def substitution_html(rows: list[dict]) -> str:
    chunks = []
    for row in rows:
        items = "".join(f"<li>{h(item)}</li>" for item in row.get("items", []))
        chunks.append(f"<div class='item'><b>{h(row.get('pattern', ''))}</b><ul>{items}</ul></div>")
    return "".join(chunks)


def sentence_rows_from_paragraphs(paragraphs: list[str], limit: int = 12) -> list[dict]:
    text = " ".join(paragraphs)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 5]
    picked = sentences[:limit]
    translations = translate_required(picked, "key sentence")
    return [{"de": s, "cn": cn} for s, cn in zip(picked, translations)]


STOPWORDS = {
    "aber",
    "alle",
    "auch",
    "auf",
    "aus",
    "bei",
    "bis",
    "das",
    "dem",
    "den",
    "der",
    "des",
    "die",
    "ein",
    "eine",
    "einem",
    "einen",
    "einer",
    "eines",
    "für",
    "hat",
    "haben",
    "hier",
    "ich",
    "ihm",
    "ihr",
    "ihre",
    "ihren",
    "ihres",
    "im",
    "in",
    "ist",
    "mit",
    "nach",
    "nicht",
    "noch",
    "oder",
    "sich",
    "sie",
    "sind",
    "und",
    "von",
    "vor",
    "war",
    "wenn",
    "wer",
    "wie",
    "wir",
    "wird",
    "werden",
    "zu",
    "zum",
    "zur",
}

SIMPLE_VOCAB = {
    "abkommen",
    "antrag",
    "audio",
    "china",
    "deutschland",
    "eu",
    "frankreich",
    "geburt",
    "gespräche",
    "iran",
    "jordanien",
    "kind",
    "kindes",
    "kinder",
    "prozent",
    "regierung",
    "russland",
    "sonntag",
    "telefonnummer",
    "trump",
    "usa",
    "irangesprächen",
    "usairangesprächen",
    "usvizepräsident",
    "usa-iran-gesprächen",
    "us-vizepräsident",
}

ADVANCED_SUFFIXES = (
    "anspruch",
    "behörde",
    "beschränkung",
    "fähigkeit",
    "frist",
    "gelder",
    "gesetz",
    "hilfe",
    "kanal",
    "kapazität",
    "leistung",
    "maßnahmen",
    "pflicht",
    "regelung",
    "sanktion",
    "stelle",
    "verfahren",
    "vereinbarung",
    "versorgung",
    "zuständigkeit",
)

KNOWN_EXPRESSION_PATTERNS = (
    (r"\bAntrag auf Elterngeld\b.*\bstellen\b", "den Antrag auf Elterngeld stellen"),
    (r"\bAntrag\b.*\bbei einer Elterngeldstelle\b.*\bstellen\b", "bei einer Elterngeldstelle stellen"),
    (r"\bElterngeld\b.*\bdigital\b.*\bbeantragen\b", "Elterngeld digital beantragen"),
    (r"\bwenden Sie sich an die Elterngeldstelle\b", "sich an die Elterngeldstelle wenden"),
    (r"\bFormular Ihres Bundeslandes\b|\bnutzen Sie\b.*\bFormular\b", "das Formular nutzen"),
    (r"\binnerhalb der ersten 3 Lebensmonate\b.*\bstellen\b", "innerhalb der ersten Lebensmonate stellen"),
    (r"\brückwirkend gezahlt\b", "rückwirkend gezahlt werden"),
    (r"\bSchritt für Schritt\b", "Schritt für Schritt"),
    (r"\bführt\b.*\bSchritt für Schritt\b.*\bdurch den Antrag\b", "Schritt für Schritt durch den Antrag führen"),
    (r"\berklärt Fachbegriffe\b", "Fachbegriffe erklären"),
    (r"\bfehlerhafte Eingaben erkennen\b", "fehlerhafte Eingaben erkennen"),
    (r"\bnehm(?:en|e|t)? Fahrt auf\b", "Fahrt aufnehmen"),
    (r"\bAbkommen\b.*\bzu erzielen\b|\bAbkommen\b.*\berzielen\b", "ein Abkommen erzielen"),
    (r"\bauf Arbeitsebene\b", "auf Arbeitsebene"),
    (r"\bhatten\b.*\bstattgefunden\b|\bhätten\b.*\bstattgefunden\b", "stattfinden"),
    (r"\bzu einem Scheitern\b.*\bführten\b|\bzu einem Scheitern\b.*\bführen\b", "zu einem Scheitern führen"),
    (r"\bKommunikationskanals?\b.*\beinrichtung\b|\bEinrichtung eines Kommunikationskanals\b", "einen Kommunikationskanal einrichten"),
    (r"\bwurde(?:n)?\b.*\bhingerichtet\b", "hingerichtet werden"),
    (r"\bbekanntgab\b|\bbekanntgegeben\b", "bekanntgeben"),
    (r"\bwegen der Tötung\b", "wegen der Tötung verurteilt werden"),
    (r"\bin Todeszellen\b", "in Todeszellen sitzen"),
    (r"\bdurchgeführt\b.*\bwerden\b|\bdurchgeführt\b", "durchgeführt werden"),
    (r"\bfortschritte\b.*\brechnen\b|\brechnet\b.*\bmit\b.*\bFortschritten\b", "mit Fortschritten rechnen"),
    (r"\bfest im Griff\b", "etwas fest im Griff haben"),
    (r"\bSanktionen\b.*\bverschärfen\b", "Sanktionen verschärfen"),
    (r"\bUnterstützung\b.*\bbewältigen\b", "Unterstützung leisten, um etwas zu bewältigen"),
    (r"\bAbhängigkeit\b.*\bverringern\b", "Abhängigkeit verringern"),
    (r"\bImport-Obergrenze\b", "eine Import-Obergrenze festlegen"),
    (r"\bmit sofortiger Wirkung\b", "mit sofortiger Wirkung in Kraft treten"),
    (r"\bRahmenabkommen\b.*\bunterzeichnet\b", "ein Rahmenabkommen unterzeichnen"),
    (r"\bSeeblockade\b.*\baufheben\b", "eine Seeblockade aufheben"),
    (r"\bWirtschaftssanktionen\b.*\bverlängert\b|\bverlängert\b.*\bWirtschaftssanktionen\b", "Wirtschaftssanktionen verlängern"),
    (r"\bentsprechende Entscheidung\b.*\btrafen\b|\bEntscheidung\b.*\btreffen\b", "eine Entscheidung treffen"),
    (r"\bBereitschaft zum Frieden\b.*\bzeigen\b", "Bereitschaft zum Frieden zeigen"),
    (r"\bfordert(?:e|en)?\b.*\bnachdrücklich auf\b", "jemanden nachdrücklich auffordern"),
    (r"\bReise\b.*\bsagt\b.*\bab\b|\bsagt\b.*\bReise\b.*\bab\b", "eine Reise absagen"),
    (r"\bZiele zur Verringerung\b.*\bsetzten\b|\bZiele zur Verringerung\b.*\bsetzen\b", "Ziele zur Verringerung setzen"),
)

KNOWN_CN = {
    "abkommen": "协议",
    "antrag": "申请；申请表",
    "beratungen": "磋商；商议",
    "bundesland": "联邦州",
    "bundesländern": "各联邦州",
    "elterngeld": "父母津贴",
    "elterngelddigital": "ElterngeldDigital 线上申请系统",
    "elterngeldstelle": "父母津贴办公室",
    "formular": "表格",
    "fortschritte": "进展",
    "geburt": "出生；分娩",
    "gespräche": "会谈；沟通",
    "hinrichtungen": "处决",
    "lebensmonate": "出生后的月龄",
    "prozent": "百分比",
    "pünktlichkeit": "准点率；准时性",
    "russland-sanktionen": "对俄罗斯制裁",
    "sanktionen": "制裁措施",
    "todesstrafe": "死刑",
    "vorgesehen": "原本计划；规定",
    "wahlbehörde": "选举管理机构",
    "wetterdienst": "气象局；气象服务机构",
    "abhängigkeit": "依赖性",
    "angriffskrieg": "侵略战争",
    "auszählung": "计票",
    "bereitschaftsdienst": "值班医疗服务",
    "dauermagneten": "永磁体",
    "einfuhr": "进口",
    "einfuhren": "进口商品；进口量",
    "einsatzleiter": "行动负责人；现场负责人",
    "führungswahl": "党内领导权选举",
    "gipfeltreffen": "峰会",
    "import-obergrenze": "进口上限",
    "lieferland": "供应国",
    "lieferungen": "交付；供应",
    "rahmenabkommen": "框架协议",
    "rohstoffeinfuhren": "原材料进口",
    "rüstungsgütern": "军备物资",
    "seeblockade": "海上封锁",
    "seltene erden": "稀土",
    "unterstützung": "支持；援助",
    "zuständig": "负责的；有管辖权的",
    "bei einer elterngeldstelle stellen": "向父母津贴办公室提交",
    "das formular nutzen": "使用表格",
    "innerhalb der ersten lebensmonate stellen": "在出生后的最初几个月内提交",
    "rückwirkend gezahlt werden": "被追溯支付",
    "schritt für schritt durch den antrag führen": "一步步引导完成申请",
    "fachbegriffe erklären": "解释专业术语",
    "fehlerhafte eingaben erkennen": "识别错误输入",
    "eine entscheidung treffen": "作出决定",
    "wirtschaftssanktionen verlängern": "延长经济制裁",
    "bereitschaft zum frieden zeigen": "表现出和平意愿",
    "jemanden nachdrücklich auffordern": "强烈敦促某人",
    "ein abkommen erzielen": "达成协议",
    "einen kommunikationskanal einrichten": "建立沟通渠道",
    "mit fortschritten rechnen": "预期会有进展",
}

KNOWN_EXPRESSION_CN = {
    "auf arbeitsebene": "在工作层面",
    "bekanntgeben": "宣布；公布",
    "das formular des bundeslandes nutzen": "使用所在联邦州的表格",
    "den antrag auf elterngeld stellen": "提交父母津贴申请",
    "durchgeführt werden": "被执行；被实施",
    "ein abkommen erzielen": "达成协议",
    "einen kommunikationskanal einrichten": "建立沟通渠道",
    "elterngeld digital beantragen": "在线申请父母津贴",
    "etwas fest im griff haben": "牢牢控制住某种局面",
    "fahrt aufnehmen": "开始加速；取得进展",
    "hingerichtet werden": "被处决",
    "in todeszellen sitzen": "被关押在死囚牢房",
    "mit fortschritten rechnen": "预期会有进展",
    "rückwirkend gezahlt werden": "被追溯支付",
    "schritt für schritt": "一步一步地",
    "sich an die elterngeldstelle wenden": "联系父母津贴办公室",
    "stattfinden": "举行；发生",
    "wegen der tötung verurteilt werden": "因杀害行为被判刑",
    "zu einem scheitern führen": "导致失败",
    "abhängigkeit verringern": "降低依赖",
    "eine import-obergrenze festlegen": "设定进口上限",
    "ein rahmenabkommen unterzeichnen": "签署框架协议",
    "mit sofortiger wirkung in kraft treten": "立即生效",
    "sanktionen verschärfen": "加重/收紧制裁",
    "unterstützung leisten, um etwas zu bewältigen": "提供支持以应对某事",
    "eine seeblockade aufheben": "解除海上封锁",
    "wirtschaftssanktionen verlängern": "延长经济制裁",
    "eine entscheidung treffen": "作出决定",
    "bereitschaft zum frieden zeigen": "表现出和平意愿",
    "jemanden nachdrücklich auffordern": "强烈敦促某人",
    "eine reise absagen": "取消行程",
    "ziele zur verringerung setzen": "设定降低/减少的目标",
    "bei einer elterngeldstelle stellen": "向父母津贴办公室提交",
    "das formular nutzen": "使用表格",
    "innerhalb der ersten lebensmonate stellen": "在出生后的最初几个月内提交",
    "schritt für schritt durch den antrag führen": "一步步引导完成申请",
    "fachbegriffe erklären": "解释专业术语",
    "fehlerhafte eingaben erkennen": "识别错误输入",
}


def split_sentences(text: str) -> list[str]:
    return [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", text)
        if len(s.strip()) >= 45 and len(s.split()) >= 6
    ]


def normalize_learning_key(value: str) -> str:
    return re.sub(r"[^a-zäöüß0-9]+", "", value.casefold())


def vocabulary_level_score(word: str) -> int:
    normalized = word.casefold().strip(" .,:;!?()[]")
    normalized_key = normalize_learning_key(normalized)
    if not normalized_key or normalized_key in SIMPLE_VOCAB or normalized_key in STOPWORDS:
        return -20
    parts = re.split(r"[\s-]+", normalized)
    score = 0
    if " " in normalized or "-" in normalized:
        score += 5
    if len(normalized_key) >= 12:
        score += 4
    elif len(normalized_key) >= 9:
        score += 2
    if any(suffix in normalized for suffix in ADVANCED_SUFFIXES):
        score += 5
    if re.search(r"(ung|heit|keit|schaft|tion|tät|nis|nahme|wende|grenze|blockade|kommen)$", normalized):
        score += 4
    if re.search(r"(staat|bundes|regierung|wirtschaft|verkehr|gesundheit|eltern|bereitschaft|kommunikation|versorgung)", normalized):
        score += 3
    if normalized[:1].isupper():
        score += 1
    if re.fullmatch(r"[A-ZÄÖÜ][a-zäöüß]+", word.strip()) and score < 5:
        score -= 3
    return score


def is_c1_vocab_candidate(word: str) -> bool:
    return vocabulary_level_score(word) >= 4


def expression_level_score(phrase: str) -> int:
    normalized = phrase.casefold().strip(" .,:;!?()[]")
    if not normalized or len(normalized.split()) < 2:
        return -10
    score = 0
    if any(marker in normalized for marker in (" in kraft ", " zur verfügung ", " anspruch auf", "antrag auf", "nach angaben", "im rahmen", "mit sofortiger wirkung")):
        score += 5
    if re.search(r"\b(?:stellen|beantragen|leisten|verschärfen|verlängern|verringern|bewältigen|unterzeichnen|aufheben|eindämmen|bekanntgeben|ankündigen|fordern|auffordern|vereinbaren|erzielen|treffen|zeigen|absagen|aufnehmen|einrichten|zuständig sein|in kraft treten)\b", normalized):
        score += 4
    if re.search(r"\b(?:maßnahmen|sanktionen|rahmenabkommen|entscheidung|abhängigkeit|unterstützung|bereitschaft|obergrenze|zuständigkeit|leistungen)\b", normalized):
        score += 3
    if len(normalized) >= 22:
        score += 1
    if normalized.startswith(("der ", "die ", "das ", "ein ", "eine ")) and not re.search(r"\b(?:stellen|treffen|leisten|zeigen|unterzeichnen|aufheben|verschärfen|verlängern|verringern|erzielen|einrichten)\b", normalized):
        score -= 2
    return score


def is_expression_candidate(phrase: str) -> bool:
    return expression_level_score(phrase) >= 4


def guess_pos(word: str) -> str:
    core = re.sub(r"^(der|die|das|ein|eine|einen|einem|einer)\s+", "", word.strip(), flags=re.I)
    if core[:1].isupper():
        return "名词"
    if re.search(r"(ung|heit|keit|schaft|tion|tät|nis)$", core, re.I):
        return "名词"
    if re.search(r"(en|ern|ieren)$", core, re.I):
        return "动词"
    if re.search(r"(lich|isch|bar|ig|los)$", core, re.I):
        return "形容词"
    return "表达/词组"


def find_example(text: str, needle: str) -> str:
    needle_key = normalize_learning_key(needle)
    for sentence in split_sentences(text):
        if needle_key and needle_key in normalize_learning_key(sentence):
            return sentence
    return split_sentences(text)[0] if split_sentences(text) else text[:180].strip()


def openai_learning_items(text: str, module: str, vocab_limit: int, expr_limit: int) -> tuple[list[dict], list[dict]] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    clipped = text[:9000]
    prompt = f"""
请只根据下面这段德语正文，为“{module}”模块抽取学习项。

硬性要求：
- 词汇和表达必须来自这段正文，不能使用旧模板、通用列表或外部材料。
- 三个模块会分别调用你，因此不要补充其他模块的内容。
- 按“曾经 C1、现在恢复德国真实阅读能力”的标准选择，不要选 A1-B1 基础词。
- 词汇不要只理解成单词，优先选择“能直接带进句子里用的语言块”：动词搭配、名词+动词框架、介词固定搭配、行政/新闻惯用结构。
- 只有当原文里确实没有足够搭配时，才补充复合名词、名词化结构、政策/行政/法律/医疗/经济/新闻中高频词。
- 表达优先选择：Funktionsverbgefüge、固定介词搭配、新闻报道固定说法、行政/法律/政策常用句式。
- 避免选择：国家名、人名、星期、普通数字词、Prozent、Antrag、Kind、Gespräch 这类单独出现时过于基础的词；如果必须选，要扩展成原文里的完整搭配。
- 返回 JSON 对象，格式：
{{
  "vocab": [
    {{"word":"德语词/短语/搭配","pos":"词性或类型中文，如固定搭配/名词化结构/复合名词","cn":"中文意思","context":"在句子里怎么用","frequency":"⭐⭐⭐/⭐⭐/⭐","example":"原文例句或贴近原文例句","example_cn":"例句中文翻译"}}
  ],
  "expressions": [
    {{"de":"德语固定搭配或高频表达","cn":"中文意思","scene":"适用场景","example":"原文例句或贴近原文例句","translation":"例句中文翻译"}}
  ]
}}
- vocab 最多 {vocab_limit} 个，expressions 最多 {expr_limit} 个。
- 优先选择能帮助用户看懂德国真实生活、新闻、医疗、育儿、行政内容的 C1 级项目。

德语正文：
{clipped}
""".strip()
    payload = json.dumps(
        {
            "model": model,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return None
    raw_text = data.get("output_text", "")
    if not raw_text:
        chunks: list[str] = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    chunks.append(content["text"])
        raw_text = "\n".join(chunks)
    raw_text = re.sub(r"^```(?:json)?|```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    vocab = normalize_vocab_rows(parsed.get("vocab", []), text, vocab_limit)
    expressions = normalize_expression_rows(parsed.get("expressions", []), text, expr_limit)
    if not vocab or not expressions:
        return None
    return vocab, expressions


def normalize_vocab_rows(rows: list[dict], text: str, limit: int) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        word = str(row.get("word", "")).strip()
        if not word:
            continue
        if not is_c1_vocab_candidate(word):
            continue
        key = normalize_learning_key(word)
        if key in seen:
            continue
        seen.add(key)
        example = str(row.get("example") or find_example(text, word)).strip()
        out.append(
            {
                "word": word,
                "pos": str(row.get("pos") or guess_pos(word)).strip(),
                "cn": str(row.get("cn") or "").strip(),
                "context": str(row.get("context") or row.get("cn") or "").strip(),
                "frequency": str(row.get("frequency") or "⭐⭐").strip(),
                "example": example,
                "example_cn": str(row.get("example_cn") or "").strip(),
            }
        )
        if len(out) >= limit:
            break
    return out


def normalize_expression_rows(rows: list[dict], text: str, limit: int) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        de = str(row.get("de", "")).strip()
        if not de:
            continue
        if not is_expression_candidate(de):
            continue
        key = normalize_learning_key(de)
        if key in seen:
            continue
        seen.add(key)
        example = str(row.get("example") or find_example(text, de)).strip()
        out.append(
            {
                "de": de,
                "cn": str(row.get("cn") or "").strip(),
                "scene": str(row.get("scene") or "理解本文和类似德国真实材料").strip(),
                "example": example,
                "translation": str(row.get("translation") or "").strip(),
            }
        )
        if len(out) >= limit:
            break
    return out


def fallback_vocab_rows(text: str, limit: int) -> list[dict]:
    usage_candidates: list[tuple[str, str]] = []
    for sentence in split_sentences(text):
        for pattern, phrase in KNOWN_EXPRESSION_PATTERNS:
            if re.search(pattern, sentence, flags=re.I) and is_expression_candidate(phrase):
                usage_candidates.append((phrase, sentence))
    usage_rows: list[dict] = []
    seen_usage: set[str] = set()
    for phrase, example in usage_candidates:
        key = normalize_learning_key(phrase)
        if not key or key in seen_usage:
            continue
        seen_usage.add(key)
        cn = KNOWN_CN.get(phrase.casefold()) or KNOWN_EXPRESSION_CN.get(phrase.casefold())
        if not cn:
            cn = translate_best_effort([phrase], "usage vocabulary")[0] or phrase
        example_cn = translate_best_effort([example], "usage vocabulary example")[0]
        usage_rows.append(
            {
                "word": phrase,
                "pos": "固定搭配/句子用法",
                "cn": cn,
                "context": f"常和原文里的动词框架一起使用：{phrase}",
                "frequency": "⭐⭐⭐",
                "example": example,
                "example_cn": example_cn,
            }
        )
        if len(usage_rows) >= limit:
            return usage_rows

    noun_phrases = re.findall(
        r"\b(?:[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+(?:-[A-ZÄÖÜA-Za-zÄÖÜäöüß]+)*\s+){0,2}"
        r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]*(?:-[A-ZÄÖÜA-Za-zÄÖÜäöüß]+)+\b",
        text,
    )
    compounds = re.findall(r"\b[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]{8,}\b|\b[a-zäöüß-]{10,}\b", text)
    words = [*noun_phrases, *compounds]
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    for word in words:
        word = base.clean_text(word).strip("- ")
        key = word.casefold()
        if not is_c1_vocab_candidate(word):
            continue
        if key.endswith(("es", "en")) and key[:-2] in STOPWORDS:
            continue
        counts[key] = counts.get(key, 0) + 1
        display.setdefault(key, word)
    ranked = sorted(
        counts,
        key=lambda key: (vocabulary_level_score(display[key]), counts[key], len(display[key])),
        reverse=True,
    )
    picked = [display[key] for key in ranked[:limit]]
    translations = translate_best_effort(picked, "content vocabulary") if picked else []
    rows = usage_rows[:]
    for word, cn in zip(picked, translations):
        if len(rows) >= limit:
            break
        if normalize_learning_key(word) in seen_usage:
            continue
        cn = KNOWN_CN.get(word.casefold(), cn)
        example = find_example(text, word)
        example_cn = translate_best_effort([example], "content vocabulary example")[0]
        rows.append(
            {
                "word": word,
                "pos": guess_pos(word),
                "cn": cn,
                "context": f"理解原文中的复合名词或名词化结构：{cn}",
                "frequency": "⭐⭐⭐" if counts[word.casefold()] > 1 else "⭐⭐",
                "example": example,
                "example_cn": example_cn,
            }
        )
    return rows


def fallback_expression_rows(text: str, limit: int, module: str) -> list[dict]:
    patterns = (
        r"\b(?:Anspruch auf|Antrag auf|Hilfe bei|Informationen zu|Informationen über)\s+[A-ZÄÖÜa-zäöüß-]+(?:\s+[A-ZÄÖÜa-zäöüß-]+){0,3}",
        r"\b(?:einen|eine|den|die|das)\s+[A-ZÄÖÜ][\wÄÖÜäöüß-]+(?:\s+[A-ZÄÖÜ][\wÄÖÜäöüß-]+)?\s+(?:stellen|beantragen|vereinbaren|absagen|vorlegen|einreichen|prüfen|ausfüllen|wählen|aufsuchen|treffen|leisten|verschärfen|verringern|unterzeichnen|aufheben)",
        r"\bsich an die [A-ZÄÖÜ][\wÄÖÜäöüß-]+(?:\s+[A-ZÄÖÜ][\wÄÖÜäöüß-]+)?\s+wenden\b",
        r"\b(?:zur Verfügung stehen|zur Verfügung stellen|in Kraft treten|mit sofortiger Wirkung|nach Angaben|im Rahmen von|Bereitschaft zum Frieden zeigen)\b",
    )
    candidates: list[tuple[str, str]] = []
    for sentence in split_sentences(text):
        for pattern, phrase in KNOWN_EXPRESSION_PATTERNS:
            if re.search(pattern, sentence, flags=re.I):
                candidates.append((phrase, sentence))
        for pattern in patterns:
            for match in re.finditer(pattern, sentence, flags=re.I):
                phrase = base.clean_text(match.group(0)).strip(" ,;:")
                if phrase.casefold().startswith("antrag auf "):
                    continue
                if is_expression_candidate(phrase):
                    candidates.append((phrase, sentence))
    rows: list[dict] = []
    seen: set[str] = set()
    for phrase, example in candidates:
        key = normalize_learning_key(phrase)
        if not key or key in seen or not is_expression_candidate(phrase):
            continue
        seen.add(key)
        rows.append({"de": phrase, "example": example})
        if len(rows) >= limit:
            break
    phrases = [row["de"] for row in rows]
    examples = [row["example"] for row in rows]
    phrase_cn = translate_best_effort(phrases, "content expression") if phrases else []
    example_cn = translate_best_effort(examples, "content expression example") if examples else []
    return [
        {
            "de": row["de"],
            "cn": KNOWN_EXPRESSION_CN.get(row["de"].casefold(), cn),
            "scene": f"{module}材料理解和类似德国真实沟通",
            "example": row["example"],
            "translation": ex_cn,
        }
        for row, cn, ex_cn in zip(rows, phrase_cn, example_cn)
    ]


def learning_items_from_text(text: str, module: str, vocab_limit: int, expr_limit: int) -> tuple[list[dict], list[dict]]:
    extracted = openai_learning_items(text, module, vocab_limit, expr_limit)
    if extracted:
        return extracted
    return fallback_vocab_rows(text, vocab_limit), fallback_expression_rows(text, expr_limit, module)


def page_link_for(date: str, page_base: str) -> str:
    return f"{page_base.rstrip('/')}/deutsch-pages/{date}.html"


def safe_page_base(page_base: str) -> str:
    lowered = (page_base or "").casefold()
    if (
        "raw.githack.com" in lowered
        or "raw.githubusercontent.com" in lowered
        or "github.com/jy0828/automation-mailer" in lowered
    ):
        return DEFAULT_PAGE_BASE
    return page_base or DEFAULT_PAGE_BASE


def details(title: str, body: str, open_: bool = False) -> str:
    attr = " open" if open_ else ""
    return f"<details{attr}><summary>{h(title)}</summary>{body}</details>"


def expr_blocks(rows: list[dict]) -> str:
    return "".join(
        f"<div class='item'><b>{h(row['de'])}</b><br>中文意思：{h(row['cn'])}<br>使用场景：{h(row['scene'])}<br>德语例句：{h(row['example'])}<br>中文翻译：{h(row['translation'])}</div>"
        for row in rows
    )


def vocab_blocks(rows: list[dict]) -> str:
    return "".join(
        f"<div class='item'><b>{h(row['word'])}</b><br>类型：{h(row['pos'])}<br>中文意思：{h(row['cn'])}<br>在句子里怎么用：{h(row['context'])}<br>德国生活使用频率：{h(row['frequency'])}<br>例句：{h(row['example'])}<br>中文翻译：{h(row.get('example_cn', ''))}</div>"
        for row in rows
    )


def build_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ margin:0; background:#f5f7fa; color:#172033; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","Microsoft YaHei",Arial,sans-serif; font-size:17px; line-height:1.68; }}
    main {{ max-width:780px; margin:0 auto; padding:18px 14px 48px; }}
    header {{ background:#172033; color:#fff; padding:22px 18px; border-radius:8px; }}
    h1 {{ font-size:24px; line-height:1.25; margin:0 0 8px; }}
    h2 {{ font-size:21px; margin:26px 0 12px; }}
    h3 {{ font-size:18px; margin:18px 0 8px; }}
    section {{ background:#fff; border:1px solid #e3e8ef; border-radius:8px; padding:16px; margin-top:16px; }}
    details {{ border-top:1px solid #e6ebf2; padding:10px 0; }}
    details:first-of-type {{ border-top:0; }}
    summary {{ cursor:pointer; font-weight:700; color:#0f3b66; }}
    .de {{ background:#f8fafc; border-left:4px solid #64748b; padding:10px 12px; border-radius:4px; }}
    .zh {{ background:#fffaf0; border-left:4px solid #f59e0b; padding:10px 12px; border-radius:4px; }}
    .item {{ background:#f8fafc; border:1px solid #e6ebf2; border-radius:8px; padding:11px 12px; margin:10px 0; }}
    .meta {{ margin:4px 0; color:#d8e4f0; }}
    .theme {{ margin-top:14px; font-weight:700; }}
    a {{ color:#0b66c3; overflow-wrap:anywhere; }}
    .muted {{ color:#5f6b7a; }}
    @media (max-width: 520px) {{ body {{ font-size:16px; }} main {{ padding:10px 10px 36px; }} section {{ padding:13px; }} h1 {{ font-size:22px; }} }}
  </style>
</head>
<body><main>{body}</main></body>
</html>"""


def raw_github_page_url(page_url: str) -> str:
    match = re.search(r"https://github\.com/([^/]+/[^/]+)/blob/main/(outputs/deutsch-pages/\d{4}-\d{2}-\d{2}\.html)", page_url)
    if match:
        return f"https://raw.githubusercontent.com/{match.group(1)}/main/{match.group(2)}"
    return page_url


def strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", value or "")).strip()


def extract_public_page_summary(page_url: str) -> dict | None:
    raw_url = raw_github_page_url(page_url)
    try:
        raw, error = fetch_raw(raw_url)
    except Exception:
        return None
    if error or not raw:
        return None
    h1 = strip_tags(re.search(r"<h1>(.*?)</h1>", raw, re.S).group(1)) if re.search(r"<h1>(.*?)</h1>", raw, re.S) else ""
    topic_match = re.search(r'<p class="theme">今日主题：(.*?)</p>', raw, re.S)
    intro_match = re.search(r"一句话简介：(.*?)</p>", raw, re.S)
    listening_pos = raw.find("<h2>2. 今日听力</h2>")
    reading_pos = raw.find("<h2>3. 今日阅读</h2>")
    listening_title = ""
    reading_title = ""
    if listening_pos >= 0:
        listening_chunk = raw[listening_pos : raw.find("<section>", listening_pos + 1) if raw.find("<section>", listening_pos + 1) >= 0 else len(raw)]
        match = re.search(r"<p><b>(.*?)</b></p>", listening_chunk, re.S)
        listening_title = strip_tags(match.group(1)) if match else ""
    if reading_pos >= 0:
        reading_chunk = raw[reading_pos : raw.find("<section>", reading_pos + 1) if raw.find("<section>", reading_pos + 1) >= 0 else len(raw)]
        match = re.search(r"<p><b>(.*?)</b></p>", reading_chunk, re.S)
        reading_title = strip_tags(match.group(1)) if match else ""
    if not (h1 and topic_match and intro_match and listening_title and reading_title):
        return None
    return {
        "display_title": h1,
        "topic": strip_tags(topic_match.group(1)),
        "intro": strip_tags(intro_match.group(1)),
        "listening_title": listening_title,
        "reading_title": reading_title,
    }


def short_outputs_from_summary(subject: str, page_url: str, summary: dict) -> tuple[str, str, str]:
    text = f"""{subject}

今日主题：
{summary["topic"]}

一句话简介：
{summary["intro"]}

今日听力：
{summary["listening_title"]}

今日阅读：
{summary["reading_title"]}

完整内容：
打开今日学习页： {page_url}
"""
    html_body = build_page(
        subject,
        f"""
<header><h1>{h(subject)}</h1><p>完整学习页入口</p></header>
<section>
  <h2>今日主题</h2><p>{h(summary["topic"])}</p>
  <h2>一句话简介</h2><p>{h(summary["intro"])}</p>
  <h2>今日听力</h2><p>{h(summary["listening_title"])}</p>
  <h2>今日阅读</h2><p>{h(summary["reading_title"])}</p>
  <p><a href="{h(page_url)}">打开今日完整学习页</a></p>
</section>
""",
    )
    telegram = f"""<b>{tg(subject)}</b>

<b>今日主题：</b>
{tg(summary["topic"])}

<b>一句话简介：</b>
{tg(summary["intro"])}

<b>今日听力：</b>
{tg(summary["listening_title"])}

<b>今日阅读：</b>
{tg(summary["reading_title"])}

<b>完整内容：</b>
打开今日学习页： {tg(page_url)}
"""
    return html_body, text, telegram


def build_daily_v5(sequence: int, today, history: list[dict], mode: str, page_base: str) -> tuple[str, str, str, str, dict, Path]:
    weekend = mode == "saturday"
    date = today.isoformat()
    display_title = f"🇩🇪 今日德语 #{sequence:03d}"
    subject = f"{display_title} - {date}"
    page_url = page_link_for(date, page_base)

    life = choose_life_article(history)
    listening = choose_dw_slow_news(300, require_audio=True, history=history, history_keys=("listening_link",))
    reading = choose_reading_article(preferred=None, skip_url=listening["url"], history=history)
    life_flat = life["paragraphs"]
    listening_flat = flatten_sections(listening["sections"])
    reading_flat = flatten_sections(reading["sections"])
    if len(life.get("dialogue", [])) < 5:
        raise RuntimeError("Life text failed quality check.")
    if sum(len(p) for p in listening_flat) < 300:
        raise RuntimeError("Listening text failed quality check.")
    if sum(len(p) for p in reading_flat) < 500:
        raise RuntimeError("Reading text failed quality check.")
    listening_translation = translate_required(listening_flat, "listening")
    reading_translation = translate_required(reading_flat, "reading")

    life_text = " ".join(life_flat)
    listening_text = " ".join(listening_flat)
    reading_text = " ".join(reading_flat)
    life_vocab, life_expr = learning_items_from_text(life_text, "今日生活场景", 12, 8)
    listening_vocab, listening_expr = learning_items_from_text(listening_text, "今日听力", 8, 8)
    reading_words = sum(len(p.split()) for p in reading_flat)
    reading_vocab_limit = 10 if reading_words < 350 else 15 if reading_words < 900 else 20
    reading_expr_limit = 8 if reading_words < 350 else 12 if reading_words < 900 else 15
    reading_vocab, reading_expr = learning_items_from_text(
        reading_text,
        "今日阅读",
        reading_vocab_limit,
        reading_expr_limit,
    )

    life_original_html = life_dialogue_html(life["dialogue"])
    life_translation_html = life_dialogue_translation_html(life["dialogue"])
    useful_html = useful_sentence_html(life.get("useful", []))
    substitutions = substitution_html(life.get("substitution", []))
    listening_keys = sentence_rows_from_paragraphs(listening_flat, 12)
    listening_key_html = "".join(
        f"<div class='item'><b>德语：</b> {h(row['de'])}<br><b>中文：</b> {h(row['cn'])}</div>"
        for row in listening_keys
    )
    listening_translation_html = translated_html(listening_flat, listening_translation)
    reading_translation_html = translated_html(reading_flat, reading_translation)
    listening_summary = openai_brief_summary(listening["title"], listening_text, "今日听力") or fallback_brief_summary(
        listening_translation,
        listening["title"],
    )
    reading_summary = openai_brief_summary(reading["title"], reading_text, "今日阅读") or fallback_brief_summary(
        reading_translation,
        reading["title"],
    )
    life_summary = f"生活场景练习{life['theme']}，重点是德国真实生活中能直接开口使用的对话。"
    top_intro = (
        f"{life_summary} 听力讲：{listening_summary} 阅读讲：{reading_summary}"
    )
    life_vocab_html = details("重点词汇", vocab_blocks(life_vocab), False) if life_vocab else ""
    life_expr_html = details("高频表达", expr_blocks(life_expr), False) if life_expr else ""

    page_body = f"""
<header>
  <h1>{h(display_title)}</h1>
  <p class="meta">{h(date)}</p>
  <p class="theme">今日主题：{h(life["topic"])}</p>
  <p>一句话简介：{h(top_intro)}</p>
</header>
<section>
  <h2>1. 今日生活场景</h2>
  <p><b>来源：</b>{h(life["source"])}<br><b>主题：</b>{h(life["theme"])}<br><b>原文链接：</b><a href="{h(life["url"])}">{h(life["url"])}</a></p>
  <h3>场景介绍</h3>
  <p>{h(life["intro"])}</p>
  {details("德语原始对话", life_original_html, True)}
  {details("中文翻译", f"<div class='zh'>{life_translation_html}</div>", True)}
  {details("今日最实用的5句", useful_html, True)}
  {details("替换练习", substitutions, False)}
  {life_vocab_html}
  {life_expr_html}
</section>
<section>
  <h2>2. 今日听力</h2>
  <p><b>{h(listening['title'])}</b></p>
  <p>音频链接：<a href="{h(listening['audio_url'])}">{h(listening['audio_url'])}</a></p>
  <p>正文来源：<a href="{h(listening['url'])}">{h(listening['url'])}</a></p>
  {details("内容导读", f"<p>{h(listening_summary)}</p><p>这是一段慢速新闻材料，适合先看全文和译文，再带着关键词去听音频。重点不是背新闻，而是训练你快速识别德国公共语境里的机构、动作和影响。</p>", True)}
  {details("完整德语正文", sections_html(listening["sections"]), True)}
  {details("逐段中文翻译", f"<div class='zh'>{listening_translation_html}</div>", True)}
  {details("关键句 8-12 句", listening_key_html, False)}
  {details("高频词汇", vocab_blocks(listening_vocab), False)}
  {details("重点表达", expr_blocks(listening_expr), False)}
  {details("听力难度说明", "<p>B1-B2。DW Langsam Gesprochene Nachrichten 语速较慢、发音清楚，但新闻词汇、被动句和长名词结构仍需要适应。</p>", True)}
</section>
<section>
  <h2>3. 今日阅读</h2>
  <p><b>{h(reading['title'])}</b></p>
  <p><a href="{h(reading['url'])}">{h(reading['url'])}</a></p>
  {details("完整德语正文", sections_html(reading["sections"]), True)}
  {details("逐段中文翻译", f"<div class='zh'>{reading_translation_html}</div>", True)}
  {details("重点词汇", vocab_blocks(reading_vocab), False)}
  {details("高频表达", expr_blocks(reading_expr), False)}
  {details("德国生活背景解释", f"<p>{h(reading_summary)}</p><p>这类材料适合恢复德国公共生活阅读能力：先抓机构、动作和影响，再看原因与后果。遇到政策、医疗、教育和行政词时，优先理解它在德国生活中的实际作用。</p>", True)}
</section>
"""
    page_html = build_page(subject, page_body)
    page_path = Path("outputs") / "deutsch-pages" / f"{date}.html"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(page_html, encoding="utf-8")

    short_text = f"""{subject}

今日主题：
{life["topic"]}

一句话简介：
{top_intro}

今日听力：
{listening['title']}

今日阅读：
{reading['title']}

完整内容：
打开今日学习页： {page_url}
"""
    short_html = build_page(
        subject,
        f"""
<header><h1>{h(subject)}</h1><p>完整学习页入口</p></header>
<section>
  <h2>今日主题</h2><p>{h(life["topic"])}</p>
  <h2>一句话简介</h2><p>{h(top_intro)}</p>
  <h2>今日听力</h2><p>{h(listening['title'])}</p>
  <h2>今日阅读</h2><p>{h(reading['title'])}</p>
  <p><a href="{h(page_url)}">打开今日完整学习页</a></p>
</section>
""",
    )
    telegram = f"""<b>{tg(subject)}</b>

<b>今日主题：</b>
{tg(life["topic"])}

<b>一句话简介：</b>
{tg(top_intro)}

<b>今日听力：</b>
{tg(listening['title'])}

<b>今日阅读：</b>
{tg(reading['title'])}

<b>完整内容：</b>
打开今日学习页： {tg(page_url)}
"""
    if os.getenv("SYNC_SHORT_FROM_PUBLIC_PAGE", "").strip().lower() in {"1", "true", "yes"}:
        public_summary = extract_public_page_summary(page_url)
        if public_summary:
            subject = f"{public_summary['display_title']} - {date}"
            short_html, short_text, telegram = short_outputs_from_summary(subject, page_url, public_summary)
        else:
            print(f"WARN public_page_summary_unavailable url={page_url}", file=sys.stderr)
    record = {
        "sequence": sequence,
        "date": date,
        "mode": mode,
        "topic": life["theme"],
        "life_topic": life["topic"],
        "life_source": life["source"],
        "life_url": life["url"],
        "life_slice_start": life.get("slice_start", 0),
        "news_title": reading["title"],
        "news_link": reading["url"],
        "listening_title": listening["title"],
        "listening_link": listening["url"],
        "page_url": page_url,
        "page_path": str(page_path),
        "expressions": [item["de"] for item in [*life_expr, *listening_expr, *reading_expr][:3]],
        "version": "v5",
    }
    return subject, short_html, short_text, telegram, record, page_path


def resolve_mode(requested: str, today) -> str:
    if requested != "auto":
        return requested
    if today.weekday() == 5:
        return "saturday"
    if today.weekday() == 6:
        return "sunday"
    return "daily"


def write_outputs(subject: str, html_body: str, text_body: str, telegram_body: str, args: argparse.Namespace) -> None:
    Path(args.subject_output).write_text(subject + "\n", encoding="utf-8")
    Path(args.html_output).write_text(html_body, encoding="utf-8")
    Path(args.text_output).write_text(text_body, encoding="utf-8")
    Path(args.telegram_output).write_text(telegram_body, encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("auto", "daily", "saturday", "sunday"), default="auto")
    parser.add_argument("--history", default="sent_history.json")
    parser.add_argument("--page-base", default=os.getenv("PUBLIC_PAGE_BASE", DEFAULT_PAGE_BASE))
    parser.add_argument("--html-output", default="deutsch-reaktivierung-email.html")
    parser.add_argument("--text-output", default="deutsch-reaktivierung-email.txt")
    parser.add_argument("--telegram-output", default="deutsch-reaktivierung-telegram.html")
    parser.add_argument("--subject-output", default="deutsch-reaktivierung-subject.txt")
    args = parser.parse_args()
    args.page_base = safe_page_base(args.page_base)

    today = base.now_berlin().date()
    history_path = Path(args.history)
    history = base.load_history(history_path)
    sequence = base.next_sequence(history)
    mode = resolve_mode(args.mode, today)
    subject, html_body, text_body, telegram_body, record, page_path = build_daily_v5(sequence, today, history, mode, args.page_base)
    history.append(record)
    base.save_history(history_path, history)
    write_outputs(subject, html_body, text_body, telegram_body, args)
    print(f"Generated v5 mode={mode} subject={subject}")
    print(f"Page: {page_path}")
    print(f"URL: {record['page_url']}")


if __name__ == "__main__":
    main()

