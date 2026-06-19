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
NACHRICHTENLEICHT_FEED = "https://www.deutschlandfunk.de/podcast-nachrichtenleicht-der-wochenrueckblick-in-einfacher-sprache-100.xml"
LIFE_SOURCE_CANDIDATES = (
    {
        "source": "Die Techniker",
        "url": "https://www.tk.de/techniker/gesundheit-foerdern/familie/kinder-und-jugendliche/krankheiten-bei-kindern-und-jugendlichen/fieber-bei-kindern-2013166",
        "theme": "Kinderarzt: Fieber bei Kindern einschätzen und beschreiben",
        "topic": "孩子发烧时如何与 Kinderarzt 沟通",
        "keywords": ("fieber", "kind", "kinderarzt", "ärztin", "arzt", "temperatur"),
    },
    {
        "source": "116117",
        "url": "https://www.116117.de/de/aerztlicher-bereitschaftsdienst.php",
        "theme": "116117: Bereitschaftsdienst oder Notruf 112",
        "topic": "判断什么时候打 116117，什么时候打 112",
        "keywords": ("116117", "112", "bereitschaftsdienst", "beschwerden", "praxis", "notfall"),
    },
    {
        "source": "Familienportal des Bundes",
        "url": "https://familienportal.de/familienportal/familienleistungen/elterngeld/faq/wie-kann-ich-elterngeld-beantragen--124762",
        "theme": "Elterngeld beantragen",
        "topic": "申请 Elterngeld 时要注意时间和材料",
        "keywords": ("elterngeld", "antrag", "geburt", "lebensmonate", "beantragen"),
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


def choose_dw_slow_news(minimum_chars: int, require_audio: bool, skip_url: str | None = None) -> dict:
    for url in dw_slow_news_candidates():
        if skip_url and url == skip_url:
            continue
        article = dw_article_from_url(url)
        if not article:
            continue
        if require_audio and not article["audio_url"]:
            continue
        if quality_ok(article["sections"], minimum_chars):
            return article
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


def choose_reading_article(skip_url: str | None = None) -> dict:
    # Nachrichtenleicht is intentionally probed but not accepted here yet: the current
    # pages often mix teaser text with Deutschlandfunk navigation/topic blocks. That is
    # worse than switching sources, so use the full-text DW fallback.
    _ = nachrichtenleicht_candidates()
    return choose_dw_slow_news(500, require_audio=False, skip_url=skip_url)


def choose_life_article() -> dict:
    for candidate in LIFE_SOURCE_CANDIDATES:
        paragraphs, error = extract_article_paragraphs(candidate["url"], None)
        if error:
            continue
        paragraphs = relevant_life_paragraphs(paragraphs, candidate["keywords"])
        text = " ".join(paragraphs)
        if len(text) < 500:
            continue
        return {
            **candidate,
            "paragraphs": paragraphs[:8],
            "sections": [{"heading": candidate["theme"], "paragraphs": paragraphs[:8]}],
        }
    raise RuntimeError("No complete life source article passed quality checks.")


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


def sentence_rows_from_paragraphs(paragraphs: list[str], limit: int = 12) -> list[dict]:
    text = " ".join(paragraphs)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 5]
    picked = sentences[:limit]
    translations = translate_required(picked, "key sentence")
    return [{"de": s, "cn": cn} for s, cn in zip(picked, translations)]


def dynamic_vocab(helpers: list[dict], paragraphs: list[str]) -> list[dict]:
    words = sum(len(p.split()) for p in paragraphs)
    limit = 10 if words < 350 else 15 if words < 900 else 20
    minimum = 8 if words < 350 else 10 if words < 900 else 15
    return base.expanded_vocabulary_rows(helpers, minimum=minimum, limit=limit)


def vocab_from_text(text: str, limit: int) -> list[dict]:
    helpers = [item for item in base.VOCAB_CANDIDATES if base.matches_helper(item, text.casefold())]
    return dynamic_vocab(helpers, [text])[:limit]


def unique_takeaways(primary: list[dict], extras: list[dict], limit: int = 3) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for item in [*primary, *extras]:
        expr = str(item.get("expr") or item.get("de") or item.get("word") or "").strip()
        if not expr:
            continue
        key = re.sub(r"^(der|die|das|ein|eine)\s+", "", expr.casefold()).strip()
        key = re.sub(r"\W+", "", key)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "expr": expr,
                "cn": item.get("cn", item.get("meaning", "")),
                "example": item.get("example", ""),
                "translation": item.get("translation", ""),
            }
        )
        if len(rows) >= limit:
            return rows
    return rows


def page_link_for(date: str, page_base: str) -> str:
    return f"{page_base.rstrip('/')}/deutsch-pages/{date}.html"


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
        f"<div class='item'><b>{h(row['word'])}</b><br>词性：{h(row['pos'])}<br>中文意思：{h(row['cn'])}<br>本文中的意思：{h(row['context'])}<br>德国生活使用频率：{h(row['frequency'])}<br>例句：{h(row['example'])}</div>"
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


def build_daily_v5(sequence: int, today, history: list[dict], mode: str, page_base: str) -> tuple[str, str, str, str, dict, Path]:
    weekend = mode == "saturday"
    date = today.isoformat()
    display_title = f"🇩🇪 今日德语 #{sequence:03d}"
    subject = f"{display_title} - {date}"
    page_url = page_link_for(date, page_base)

    life = choose_life_article()
    scenario = choose_scenario_for_life(life, history, weekend=weekend)
    listening = choose_dw_slow_news(300, require_audio=True)
    reading = choose_reading_article(skip_url=listening["url"])
    life_flat = life["paragraphs"]
    listening_flat = flatten_sections(listening["sections"])
    reading_flat = flatten_sections(reading["sections"])
    if sum(len(p) for p in life_flat) < 500:
        raise RuntimeError("Life text failed quality check.")
    if sum(len(p) for p in listening_flat) < 300:
        raise RuntimeError("Listening text failed quality check.")
    if sum(len(p) for p in reading_flat) < 500:
        raise RuntimeError("Reading text failed quality check.")
    life_translation = translate_required(life_flat, "life")
    listening_translation = translate_required(listening_flat, "listening")
    reading_translation = translate_required(reading_flat, "reading")

    expressions = base.expression_rows(scenario["expressions"])
    scenario_expr = base.expression_detail_rows(expressions, scenario)
    life_text = " ".join(life_flat)
    listening_text = " ".join(listening_flat)
    reading_text = " ".join(reading_flat)
    life_vocab = vocab_from_text(life_text, 12)
    listening_vocab = vocab_from_text(listening_text, 5)
    reading_vocab = dynamic_vocab(
        [item for item in base.VOCAB_CANDIDATES if base.matches_helper(item, reading_text.casefold())],
        reading_flat,
    )
    listening_expr = base.news_expression_rows()[:3]
    reading_expr = base.news_expression_rows()[:12]
    takeaways = unique_takeaways(scenario_expr, [*life_vocab, *listening_vocab, *reading_vocab])

    dialogue = base.dialogue_text(scenario["dialogue"])
    reusable = base.reusable_sentence_rows(scenario)
    reusable_html = "".join(
        f"<div class='item'><b>德语：</b> {h(row['de'])}<br><b>中文：</b> {h(row['cn'])}<br><b>适用场景：</b> {h(row['scene'])}</div>"
        for row in reusable
    )
    listening_keys = sentence_rows_from_paragraphs(listening_flat, 12)
    listening_key_html = "".join(
        f"<div class='item'><b>德语：</b> {h(row['de'])}<br><b>中文：</b> {h(row['cn'])}</div>"
        for row in listening_keys
    )
    life_translation_html = translated_html(life_flat, life_translation)
    listening_translation_html = translated_html(listening_flat, listening_translation)
    reading_translation_html = translated_html(reading_flat, reading_translation)
    takeaway_html = "".join(
        f"<div class='item'><b>{h(item['expr'])}</b><br>中文意思：{h(item['cn'])}<br>例句：{h(item['example'])}<br>中文翻译：{h(item['translation'])}</div>"
        for item in takeaways
    )

    page_body = f"""
<header>
  <h1>{h(display_title)}</h1>
  <p class="meta">{h(date)}</p>
  <p class="theme">今日主题：{h(life["topic"])}</p>
  <p>一句话简介：学习德国真实页面里关于{h(life["theme"])}的常用说法，降低今天读懂和开口沟通的成本。</p>
</header>
<section>
  <h2>1. 今日生活场景</h2>
  <p><b>来源：</b>{h(life["source"])}<br><b>主题：</b>{h(life["theme"])}<br><b>原文链接：</b><a href="{h(life["url"])}">{h(life["url"])}</a></p>
  {details("原始内容", sections_html(life["sections"]), True)}
  {details("中文翻译", f"<div class='zh'>{life_translation_html}</div>", True)}
  {details("重点词汇", vocab_blocks(life_vocab), False)}
  {details("高频表达", expr_blocks(scenario_expr), False)}
  {details("德国人会怎么说", reusable_html, False)}
</section>
<section>
  <h2>2. 今日听力</h2>
  <p><b>{h(listening['title'])}</b></p>
  <p>音频链接：<a href="{h(listening['audio_url'])}">{h(listening['audio_url'])}</a></p>
  <p>正文来源：<a href="{h(listening['url'])}">{h(listening['url'])}</a></p>
  {details("内容导读", "<p>这是一段慢速新闻材料，适合先看全文和译文，再带着关键词去听音频。重点不是背新闻，而是训练你快速识别德国公共语境里的机构、动作和影响。</p>", True)}
  {details("完整德语正文", sections_html(listening["sections"]), True)}
  {details("逐段中文翻译", f"<div class='zh'>{listening_translation_html}</div>", True)}
  {details("关键句 8-12 句", listening_key_html, False)}
  {details("高频词汇（5个）", vocab_blocks(listening_vocab), False)}
  {details("重点表达（3个）", expr_blocks(listening_expr), False)}
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
  {details("德国生活背景解释", "<p>这类材料适合恢复德国公共生活阅读能力：先抓机构、动作和影响，再看原因与后果。遇到政策、医疗、教育和行政词时，优先理解它在德国生活中的实际作用。</p>", True)}
</section>
<section>
  <h2>今天只记住这 3 个</h2>
  {takeaway_html}
</section>
"""
    page_html = build_page(subject, page_body)
    page_path = Path("outputs") / "deutsch-pages" / f"{date}.html"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(page_html, encoding="utf-8")

    takeaways_text = "\n".join(f"{idx}. {item['expr']}" for idx, item in enumerate(takeaways, 1))
    short_text = f"""{subject}

今日主题：
{life["topic"]}

今日听力：
{listening['title']}

今日阅读：
{reading['title']}

今日只记住这 3 个：
{takeaways_text}

完整内容：
打开今日学习页： {page_url}
"""
    short_html = build_page(
        subject,
        f"""
<header><h1>{h(subject)}</h1><p>完整学习页入口</p></header>
<section>
  <h2>今日主题</h2><p>{h(life["topic"])}</p>
  <h2>今日听力</h2><p>{h(listening['title'])}</p>
  <h2>今日阅读</h2><p>{h(reading['title'])}</p>
  <h2>今日只记住这 3 个</h2><pre>{h(takeaways_text)}</pre>
  <p><a href="{h(page_url)}">打开今日完整学习页</a></p>
</section>
""",
    )
    telegram = f"""<b>{tg(subject)}</b>

<b>今日主题：</b>
{tg(life["topic"])}

<b>今日听力：</b>
{tg(listening['title'])}

<b>今日阅读：</b>
{tg(reading['title'])}

<b>今日只记住这 3 个：</b>
{tg(takeaways_text)}

<b>完整内容：</b>
打开今日学习页： {tg(page_url)}
"""
    record = {
        "sequence": sequence,
        "date": date,
        "mode": mode,
        "topic": scenario["topic"],
        "news_title": reading["title"],
        "news_link": reading["url"],
        "listening_title": listening["title"],
        "listening_link": listening["url"],
        "page_url": page_url,
        "page_path": str(page_path),
        "expressions": [item["expr"] for item in takeaways],
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


