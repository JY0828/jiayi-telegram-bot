#!/usr/bin/env python3
"""Generate Deutsch Reaktivierung v5: short push plus a static detail page."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import generate_deutsch_reactivation_email as base


DEFAULT_PAGE_BASE = "https://jy0828.github.io/jiayi-telegram-bot"


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
        if tag in {"p", "li", "h2", "h3"}:
            self._stack.append(tag)
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        if self._stack[-1] == tag:
            if tag in {"p", "li", "h2", "h3"}:
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
        if self._stack[-1] in {"p", "li", "h2", "h3"}:
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
    )
    return sum(marker in lowered for marker in noisy) == 0


def fetch_raw(url: str) -> tuple[str, str | None]:
    try:
        return base.fetch_text(url, timeout=25), None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return "", str(exc)


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
        return [], "未配置 OPENAI_API_KEY，无法生成逐段中文翻译。"
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
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [], f"翻译请求失败：{exc}"
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
        return [], "翻译结果格式不稳定，因此不展示可能错位的全文翻译。"
    return [str(item).strip() for item in translated], None


def sentence_rows_from_paragraphs(paragraphs: list[str], limit: int = 12) -> list[dict]:
    text = " ".join(paragraphs)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 5]
    return [{"de": s, "cn": "逐句内容仅在获取到完整字幕/正文时生成。"} for s in sentences[:limit]]


def dynamic_vocab(helpers: list[dict], paragraphs: list[str]) -> list[dict]:
    words = sum(len(p.split()) for p in paragraphs)
    limit = 10 if words < 350 else 15 if words < 900 else 20
    minimum = 8 if words < 350 else 10 if words < 900 else 15
    return base.expanded_vocabulary_rows(helpers, minimum=minimum, limit=limit)


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
    a {{ color:#0b66c3; overflow-wrap:anywhere; }}
    .muted {{ color:#5f6b7a; }}
    @media (max-width: 520px) {{ body {{ font-size:16px; }} main {{ padding:10px 10px 36px; }} section {{ padding:13px; }} h1 {{ font-size:22px; }} }}
  </style>
</head>
<body><main>{body}</main></body>
</html>"""


def build_daily_v5(sequence: int, today, history: list[dict], mode: str, page_base: str) -> tuple[str, str, str, str, dict, Path]:
    weekend = mode == "saturday"
    scenario = base.choose_scenario(history, weekend=weekend)
    news = base.choose_item(base.NEWS_FEEDS, history, base.fallback_news())
    listening = base.choose_item(base.LISTENING_FEEDS, history, base.fallback_listening())
    date = today.isoformat()
    subject = f"🇩🇪 今日德语 #{sequence:03d} - {date}"
    page_url = page_link_for(date, page_base)

    news_paragraphs, news_error = extract_article_paragraphs(news.link, news)
    news_is_full_article = bool(news_paragraphs) and not news_error
    news_translations, translation_error = translate_paragraphs(news_paragraphs) if news_is_full_article else ([], None)
    listening_paragraphs, listening_error = extract_article_paragraphs(listening.link, listening)

    helpers, video_helpers = base.reading_helpers(news, listening)
    expressions = base.expression_rows(scenario["expressions"])
    scenario_expr = base.expression_detail_rows(expressions, scenario)
    news_vocab = dynamic_vocab(helpers, news_paragraphs)
    news_expr = base.news_expression_rows()
    takeaways = base.takeaways(scenario_expr, news_vocab)

    dialogue = base.dialogue_text(scenario["dialogue"])
    reusable = base.reusable_sentence_rows(scenario)
    reusable_html = "".join(
        f"<div class='item'><b>德语：</b> {h(row['de'])}<br><b>中文：</b> {h(row['cn'])}<br><b>适用场景：</b> {h(row['scene'])}</div>"
        for row in reusable
    )
    takeaway_html = "".join(
        f"<div class='item'><b>{h(item['expr'])}</b><br>中文意思：{h(item['cn'])}<br>例句：{h(item['example'])}<br>中文翻译：{h(item['translation'])}</div>"
        for item in takeaways
    )

    if listening_paragraphs:
        listening_intro = "本模块基于已抓取到的视频/音频页面文本。若页面文本不是逐字字幕，只作为听前导读使用。"
        listening_keys = sentence_rows_from_paragraphs(listening_paragraphs, 12)
        listening_key_html = "".join(
            f"<div class='item'><b>德语：</b> {h(row['de'])}<br><b>中文：</b> {h(row['cn'])}</div>"
            for row in listening_keys
        )
    else:
        listening_intro = f"未能获取完整字幕，因此本模块只基于页面文本和标题，不生成伪造逐句内容。失败原因：{listening_error or '页面未提供可提取的字幕或正文段落。'}"
        listening_key_html = "<p class='muted'>未生成关键句，避免编造视频原文。</p>"

    if news_paragraphs:
        original_html = "".join(f"<p>{h(p)}</p>" for p in news_paragraphs)
        if news_translations:
            translation_html = "".join(f"<p>{h(p)}</p>" for p in news_translations)
        elif not news_is_full_article:
            translation_html = f"<p class='muted'>正文抓取失败，本次只提供标题和简介，不提供全文翻译。失败原因：{h(news_error or '未抓到完整正文。')}</p>"
        else:
            translation_html = f"<p class='muted'>已抓取正文，但未生成全文翻译。原因：{h(translation_error or '未知错误')}</p>"
    else:
        original_html = f"<p class='muted'>正文抓取失败，本次只提供标题和简介，不提供全文翻译。失败原因：{h(news_error or '未知错误')}</p>"
        translation_html = "<p class='muted'>正文抓取失败，本次不提供全文翻译。</p>"

    page_body = f"""
<header>
  <h1>{h(subject)}</h1>
  <p>轻推送 + 详情页版。推送只做入口，完整内容在这里阅读。</p>
</header>
<section>
  <h2>1. 今日生活场景</h2>
  <p>{h(scenario["intro"])}</p>
  {details("德语原对话", f"<div class='de'><pre>{h(dialogue)}</pre></div>", True)}
  {details("中文翻译", f"<div class='zh'>{h(scenario['translation'])}</div>", True)}
  {details("可直接复用句子", reusable_html, False)}
  {details("高频表达", expr_blocks(scenario_expr), False)}
  {details("今天最值得记住的表达", takeaway_html, True)}
</section>
<section>
  <h2>2. 今日听力</h2>
  <p><b>{h(listening.title)}</b></p>
  <p><a href="{h(listening.link)}">{h(listening.link)}</a></p>
  <div class="zh">{h(listening_intro)}</div>
  {details("视频内容中文导读", f"<p>{h(base.listening_guide(listening, ' '.join(listening_paragraphs)))}</p>", True)}
  {details("视频关键句", listening_key_html, False)}
  {details("高频表达", vocab_blocks(base.vocabulary_rows(video_helpers or helpers[:5], 8)), False)}
  {details("听力难度说明", "<p>B1-B2。短内容适合恢复听力反应；如果页面没有字幕，重点放在标题、页面导读和听懂大意。</p>", True)}
</section>
<section>
  <h2>3. 今日德国新闻</h2>
  <p><b>{h(news.title)}</b></p>
  <p><a href="{h(news.link)}">{h(news.link)}</a></p>
  <p>{h(base.cn_summary(news))}</p>
  {details("原文正文", original_html, False)}
  {details("全文中文翻译", f"<div class='zh'>{translation_html}</div>", True)}
  {details("重点词汇", vocab_blocks(news_vocab), False)}
  {details("高频表达", expr_blocks(news_expr), False)}
</section>
"""
    page_html = build_page(subject, page_body)
    page_path = Path("outputs") / "deutsch-pages" / f"{date}.html"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(page_html, encoding="utf-8")

    takeaways_text = "\n".join(f"{idx}. {item['expr']}" for idx, item in enumerate(takeaways, 1))
    short_text = f"""{subject}

今日主题：
{scenario["intro"]}

今日听力：
{listening.title}

今日新闻：
{news.title}

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
  <h2>今日主题</h2><p>{h(scenario["intro"])}</p>
  <h2>今日听力</h2><p>{h(listening.title)}</p>
  <h2>今日新闻</h2><p>{h(news.title)}</p>
  <h2>今日只记住这 3 个</h2><pre>{h(takeaways_text)}</pre>
  <p><a href="{h(page_url)}">打开今日完整学习页</a></p>
</section>
""",
    )
    telegram = f"""<b>{tg(subject)}</b>

<b>今日主题：</b>
{tg(scenario["intro"])}

<b>今日听力：</b>
{tg(listening.title)}

<b>今日新闻：</b>
{tg(news.title)}

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
        "news_title": news.title,
        "news_link": news.link,
        "listening_title": listening.title,
        "listening_link": listening.link,
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
