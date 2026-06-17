#!/usr/bin/env python3
"""Generate Deutsch Reaktivierung v3 content for Email and Telegram."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo


BERLIN = ZoneInfo("Europe/Berlin")
HISTORY_LIMIT = 150


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    keywords: tuple[str, ...]
    kind: str = "article"


@dataclass(frozen=True)
class MediaItem:
    source: str
    title: str
    link: str
    summary: str
    published: str
    score: int
    kind: str = "article"


NEWS_FEEDS = (
    Feed("Tagesschau", "https://www.tagesschau.de/xml/rss2/", ("deutschland", "kita", "schule", "bildung", "gesundheit", "pflege", "familie", "kinder", "medizin", "digital", "verwaltung")),
    Feed("Deutschlandfunk", "https://www.deutschlandfunk.de/nachrichten-100.rss", ("deutschland", "bildung", "gesundheit", "gesellschaft", "familie", "forschung", "digital", "medizin")),
    Feed("Deutschlandfunk Gesellschaft", "https://www.deutschlandfunk.de/gesellschaft-106.rss", ("bildung", "gesundheit", "gesellschaft", "familie", "kinder", "schule", "pflege")),
    Feed("WDR", "https://www.wdr.de/xml/newsticker.rdf", ("nrw", "kita", "schule", "gesundheit", "familie", "verwaltung")),
    Feed("NDR", "https://www.ndr.de/index~rss2.xml", ("schule", "kita", "gesundheit", "familie", "bildung", "pflege", "norden")),
    Feed("ZDF Heute", "https://www.zdf.de/rss/zdf/nachrichten", ("deutschland", "bildung", "gesundheit", "gesellschaft", "familie", "technik", "digital")),
)

LISTENING_FEEDS: tuple[Feed, ...] = ()

OPTIONAL_REVIEW_FEEDS = (
    Feed("ZDF heute journal Video", "https://www.zdf.de/rss/podcast/video/zdf/nachrichten/heute-journal", ("heute journal", "video", "nachrichten"), "video"),
    Feed("ZDF heute 19 Uhr Video", "https://www.zdf.de/rss/podcast/video/zdf/nachrichten/heute-19-uhr", ("heute", "nachrichten", "video"), "video"),
)

PREFERRED = ("kita", "kinderarzt", "kind", "schule", "bildung", "gesundheit", "pflege", "medizin", "familie", "gesellschaft", "digital", "technik", "verwaltung", "nrw", "deutschland")
DEPRIORITIZED = ("trump", "usa", "ukraine", "russland", "israel", "iran", "krieg", "gaza", "promi", "star", "fußball", "fussball")

VOCAB_CANDIDATES = (
    {
        "word": "der Allgemeinzustand",
        "cn": "整体精神和身体状态",
        "de": "Wie es einem Kind insgesamt geht, nicht nur ein einzelnes Symptom.",
        "example": "Die Ärztin fragte zuerst nach dem Allgemeinzustand des Kindes.",
    },
    {
        "word": "ansprechbar",
        "cn": "能回应、意识清楚",
        "de": "Eine Person reagiert auf Ansprache und wirkt nicht bewusstlos oder apathisch.",
        "example": "Trotz Fieber war sie ansprechbar und konnte normal trinken.",
    },
    {
        "word": "die Abklärung",
        "cn": "进一步检查/确认",
        "de": "Eine genauere Untersuchung, um die Ursache eines Problems zu finden.",
        "example": "Die Kinderärztin empfahl eine Abklärung beim Facharzt.",
    },
    {
        "word": "der Dringlichkeitscode",
        "cn": "紧急转诊码",
        "de": "Ein Code auf der Überweisung, mit dem schneller ein Facharzttermin vermittelt werden kann.",
        "example": "Mit dem Dringlichkeitscode bekam die Familie schneller einen Termin.",
    },
    {
        "word": "die Unterlagen",
        "cn": "材料、文件",
        "de": "Dokumente, die man für einen Termin oder Antrag braucht.",
        "example": "Bitte bringen Sie alle Unterlagen zum Termin im Bürgeramt mit.",
    },
    {
        "word": "vollständig",
        "cn": "齐全、完整",
        "de": "Alles Nötige ist vorhanden; es fehlt nichts.",
        "example": "Die Sachbearbeiterin prüfte, ob die Unterlagen vollständig sind.",
    },
    {
        "word": "die Eingewöhnung",
        "cn": "Kita 适应期",
        "de": "Die erste Zeit in der Kita, in der sich ein Kind langsam an die neue Umgebung gewöhnt.",
        "example": "Während der Eingewöhnung bleiben die Eltern am Anfang oft noch in der Nähe.",
    },
    {
        "word": "die Rückmeldung",
        "cn": "反馈、状态更新",
        "de": "Eine kurze Information darüber, wie etwas gelaufen ist.",
        "example": "Die Erzieherin gab den Eltern am Nachmittag eine kurze Rückmeldung.",
    },
    {
        "word": "die Wohnungsgeberbestätigung",
        "cn": "房东入住证明",
        "de": "Ein Formular vom Vermieter, das man für die Anmeldung beim Bürgeramt braucht.",
        "example": "Ohne Wohnungsgeberbestätigung konnte die Ummeldung nicht abgeschlossen werden.",
    },
    {
        "word": "die Meldebescheinigung",
        "cn": "住址登记证明",
        "de": "Eine offizielle Bescheinigung über die angemeldete Adresse.",
        "example": "Nach der Ummeldung bekam er direkt eine Meldebescheinigung.",
    },
    {
        "word": "die Versorgungslage",
        "cn": "供给/服务状况",
        "de": "Wie gut Menschen mit Betreuung, Medizin oder anderen Leistungen versorgt sind.",
        "example": "In vielen Regionen bleibt die medizinische Versorgungslage angespannt.",
    },
    {
        "word": "der Fachkräftemangel",
        "cn": "专业人员短缺",
        "de": "Es gibt nicht genug qualifizierte Arbeitskräfte in einem Bereich.",
        "example": "Der Fachkräftemangel macht sich besonders in Kitas und Kliniken bemerkbar.",
    },
    {
        "word": "die Geburtenrate",
        "cn": "出生率",
        "de": "Wie viele Kinder in einem Land oder einer Region geboren werden.",
        "example": "Die Geburtenrate ist in den vergangenen Jahren gesunken.",
    },
    {
        "word": "der Kinderwunsch",
        "cn": "生育意愿",
        "de": "Der Wunsch, ein Kind oder weitere Kinder zu bekommen.",
        "example": "Viele Faktoren beeinflussen den Kinderwunsch junger Familien.",
    },
    {
        "word": "die Familienpolitik",
        "cn": "家庭政策",
        "de": "Politische Maßnahmen, die Familien unterstützen sollen.",
        "example": "Gute Familienpolitik soll Eltern im Alltag entlasten.",
    },
    {
        "word": "der Betreuungsplatz",
        "cn": "托育名额",
        "de": "Ein Platz in Kita, Tagespflege oder Betreuung.",
        "example": "Viele Eltern warten lange auf einen Betreuungsplatz.",
    },
    {
        "word": "der Antrag",
        "cn": "申请",
        "de": "Ein offizielles Formular oder Gesuch bei einer Stelle.",
        "example": "Für die Leistung muss ein Antrag gestellt werden.",
    },
    {
        "word": "die Bescheinigung",
        "cn": "证明文件",
        "de": "Ein offizielles Dokument, das etwas bestätigt.",
        "example": "Für den Antrag benötigen Sie eine Bescheinigung.",
    },
    {
        "word": "beantragen",
        "cn": "申请",
        "de": "Offiziell um etwas bitten, meistens bei einer Behörde.",
        "example": "Das Elterngeld kann online beantragt werden.",
    },
    {
        "word": "zuständig",
        "cn": "负责的",
        "de": "Eine Stelle oder Person ist für etwas verantwortlich.",
        "example": "Für die Anmeldung ist das Bürgeramt zuständig.",
    },
    {
        "word": "die Bearbeitungszeit",
        "cn": "办理时间",
        "de": "Die Zeit, die eine Behörde für einen Antrag braucht.",
        "example": "Die Bearbeitungszeit kann mehrere Wochen dauern.",
    },
    {
        "word": "der Nachrichtenüberblick",
        "cn": "新闻概览",
        "de": "Eine kurze Zusammenfassung der wichtigsten Nachrichten.",
        "example": "Die Sendung bietet einen schnellen Nachrichtenüberblick.",
    },
    {
        "word": "die Sendung",
        "cn": "节目",
        "de": "Ein Audio- oder Videoformat im Radio, Fernsehen oder online.",
        "example": "Die Sendung dauert nur wenige Minuten.",
    },
)

SCENARIOS = (
    {
        "topic": "Kinderarzt",
        "intro": "孩子发烧咳嗽，你需要在 Kinderarzt 处清楚说明症状、持续时间、用药和真正担心的点。",
        "dialogue": [
            ("Elternteil", "Guten Morgen, meine Tochter hat seit Sonntag Fieber und hustet nachts ziemlich stark."),
            ("Ärztin", "Wie hoch war das Fieber ungefähr?"),
            ("Elternteil", "Gestern Abend lag es bei 39,2. Mit Ibuprofen ging es runter, kam aber nach ein paar Stunden wieder."),
            ("Ärztin", "Trinkt sie ausreichend? Und wie ist der Allgemeinzustand?"),
            ("Elternteil", "Sie trinkt weniger als sonst, aber noch regelmäßig. Tagsüber ist sie schlapp, aber ansprechbar."),
            ("Ärztin", "Hat sie Atemnot, pfeifende Atmung oder Schmerzen beim Atmen?"),
            ("Elternteil", "Atemnot nicht, aber der Husten klingt manchmal richtig fest."),
            ("Ärztin", "Ich höre sie gleich ab. Wahrscheinlich ist es ein Infekt, aber wir schauen uns die Lunge genau an."),
        ],
        "translation": "重点是先给出时间线、体温、用药后的变化，再问清楚什么情况下需要复诊或去急诊。",
        "sentences": [
            "Mein Kind hat seit ... Fieber.",
            "Mit Ibuprofen ging es runter, kam aber wieder.",
            "Sie/Er trinkt weniger als sonst.",
            "Tagsüber ist sie/er schlapp, aber ansprechbar.",
            "Ab wann müssten wir wiederkommen?",
        ],
        "expressions": [
            ("der Allgemeinzustand", "整体精神和身体状态", "儿科问诊", "der Gesamtzustand"),
            ("ansprechbar sein", "能回应，意识清楚", "判断病情紧急程度", "reagieren können"),
            ("schlapp sein", "没精神、蔫", "描述孩子状态", "kraftlos sein"),
            ("jemanden abhören", "给某人听诊", "医生检查", "die Lunge abhören"),
            ("ab wann müssten wir ...?", "什么情况下我们需要……？", "追问处理边界", "in welchem Fall sollten wir ...?"),
        ],
    },
    {
        "topic": "Kita / Eingewöhnung",
        "intro": "孩子正在 Kita Eingewöhnung，你要和 Erzieherin 沟通分离反应、午睡和接下来几天的安排。",
        "dialogue": [
            ("Elternteil", "Guten Morgen, ich wollte kurz Rückmeldung geben: Heute Morgen war er etwas angespannter als gestern."),
            ("Erzieherin", "Danke für die Info. Hat er zu Hause schon geweint oder erst beim Ankommen?"),
            ("Elternteil", "Eher beim Ankommen. Zu Hause war er noch ganz gut drauf."),
            ("Erzieherin", "Das ist in der Eingewöhnung normal. Wir schauen, ob eine kürzere Trennung besser passt."),
            ("Elternteil", "Sollen wir wieder mit zehn Minuten anfangen?"),
            ("Erzieherin", "Genau. Wenn er sich gut beruhigen lässt, können wir morgen vorsichtig verlängern."),
            ("Elternteil", "Beim Mittagsschlaf bin ich mir noch unsicher."),
            ("Erzieherin", "Dann geben Sie gerne sein Kuscheltier mit. Vertraute Dinge helfen am Anfang."),
        ],
        "translation": "重点是给老师一个短状态更新，表达担心，但不要解释过度；一起确认下一步即可。",
        "sentences": [
            "Ich wollte kurz Rückmeldung geben.",
            "Heute Morgen war er/sie etwas angespannter.",
            "Sollen wir wieder mit zehn Minuten anfangen?",
            "Beim Mittagsschlaf bin ich mir noch unsicher.",
            "Wir orientieren uns an seinem/ihrem Tempo.",
        ],
        "expressions": [
            ("gut drauf sein", "状态不错、心情可以", "描述孩子早上状态", "in guter Stimmung sein"),
            ("sich beruhigen lassen", "能被安抚下来", "谈分离后的哭闹", "sich trösten lassen"),
            ("vorsichtig verlängern", "谨慎延长", "延长分离时间", "behutsam ausweiten"),
            ("zur Ruhe kommen", "安静下来、进入休息状态", "午睡或情绪恢复", "runterkommen"),
            ("sich an seinem Tempo orientieren", "按他的节奏来", "育儿沟通", "in seinem Tempo vorgehen"),
        ],
    },
    {
        "topic": "116117 / Facharzttermin",
        "intro": "你需要通过 116117 或 Terminservicestelle 预约 Facharzt，说明转诊、紧急程度和可接受地点。",
        "dialogue": [
            ("Mitarbeiterin", "Terminservicestelle, guten Morgen. Worum geht es?"),
            ("Anrufer", "Guten Morgen, ich brauche einen Termin beim Facharzt. Ich habe eine Überweisung mit Dringlichkeitscode."),
            ("Mitarbeiterin", "Um welche Fachrichtung handelt es sich?"),
            ("Anrufer", "Kinderradiologie. Es geht um eine Abklärung nach Empfehlung der Kinderärztin."),
            ("Mitarbeiterin", "Haben Sie den Code gerade zur Hand?"),
            ("Anrufer", "Ja, einen Moment. Der Code lautet ..."),
            ("Mitarbeiterin", "In welchem Umkreis können Sie Termine wahrnehmen?"),
            ("Anrufer", "Am liebsten in Düsseldorf oder Umgebung. Wenn es schneller geht, auch weiter weg."),
        ],
        "translation": "重点是先说明有 Dringlichkeitscode，再说明 Fachrichtung、地点范围和灵活度，最后确认材料。",
        "sentences": [
            "Ich habe eine Überweisung mit Dringlichkeitscode.",
            "Es geht um eine Abklärung.",
            "In welchem Umkreis gibt es Termine?",
            "Wenn es schneller geht, können wir auch weiter fahren.",
            "Welche Unterlagen müssen wir mitbringen?",
        ],
        "expressions": [
            ("eine Abklärung", "进一步检查/确认", "专科检查", "eine genauere Untersuchung"),
            ("zur Hand haben", "手边有、能马上提供", "电话里提供号码", "griffbereit haben"),
            ("im Umkreis", "周边范围内", "找医生/办事地点", "in der Umgebung"),
            ("zeitlich schneller gehen", "时间上更快", "比较预约时间", "früher klappen"),
            ("verbindlich gebucht", "已正式预约", "确认预约", "fest eingetragen"),
        ],
    },
    {
        "topic": "Bürgeramt",
        "intro": "你在 Bürgeramt 办 Anmeldung 或证件事务，需要确认材料是否齐全，以及是否还需要补交文件。",
        "dialogue": [
            ("Sachbearbeiterin", "Guten Morgen. Haben Sie einen Termin?"),
            ("Antragsteller", "Ja, um 8:20 Uhr. Es geht um die Ummeldung."),
            ("Sachbearbeiterin", "Dann brauche ich bitte Ihren Ausweis und die Wohnungsgeberbestätigung."),
            ("Antragsteller", "Hier sind die Unterlagen. Können Sie kurz prüfen, ob alles vollständig ist?"),
            ("Sachbearbeiterin", "Die Wohnungsgeberbestätigung passt. Der Mietvertrag ist dafür nicht nötig."),
            ("Antragsteller", "Gut. Bekomme ich direkt eine Meldebescheinigung?"),
            ("Sachbearbeiterin", "Ja, die kann ich Ihnen gleich ausdrucken."),
            ("Antragsteller", "Super, vielen Dank. Muss ich sonst noch etwas beachten?"),
        ],
        "translation": "重点是短句确认：预约、事项、材料、是否完整、是否能直接拿到 Bescheinigung。",
        "sentences": [
            "Ich habe einen Termin um ...",
            "Es geht um die Ummeldung.",
            "Können Sie kurz prüfen, ob alles vollständig ist?",
            "Bekomme ich direkt eine Meldebescheinigung?",
            "Muss ich sonst noch etwas beachten?",
        ],
        "expressions": [
            ("die Unterlagen", "材料/文件", "行政办事", "die Dokumente"),
            ("vollständig sein", "齐全", "检查材料", "komplett sein"),
            ("nicht nötig sein", "不需要", "确认材料要求", "nicht erforderlich sein"),
            ("gleich ausdrucken", "马上打印", "柜台办理", "direkt ausdrucken"),
            ("etwas beachten müssen", "需要注意某事", "办完事确认后续", "auf etwas achten müssen"),
        ],
    },
)


def now_berlin() -> dt.datetime:
    override = os.getenv("RUN_DATE")
    if override:
        return dt.datetime.fromisoformat(override).replace(tzinfo=BERLIN)
    return dt.datetime.now(BERLIN)


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "automation-mailer Deutsch Reaktivierung v3"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def fetch_page_content(url: str) -> str:
    try:
        raw = fetch_text(url, timeout=20)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"WARN page_fetch_failed url={url} error={exc}", file=sys.stderr)
        return ""
    raw = re.sub(r"(?is)<script.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style.*?</style>", " ", raw)
    raw = re.sub(r"(?is)<noscript.*?</noscript>", " ", raw)
    return clean_text(raw)


def child_text(item: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        found = item.find(name)
        if found is not None and found.text:
            return found.text
    for child in item:
        tag = child.tag.split("}", 1)[-1]
        if tag in names and child.text:
            return child.text
    return ""


def parse_date(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).astimezone(BERLIN).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OverflowError):
        return clean_text(value)


def parse_feed(feed: Feed) -> list[MediaItem]:
    try:
        root = ET.fromstring(fetch_text(feed.url))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, ET.ParseError) as exc:
        print(f"WARN fetch_failed source={feed.name} error={exc}", file=sys.stderr)
        return []
    items: list[MediaItem] = []
    for item in root.findall(".//item")[:20]:
        title = clean_text(child_text(item, ("title",)))
        summary = clean_text(child_text(item, ("description", "encoded", "summary")))
        link = clean_text(child_text(item, ("link", "guid")))
        published = parse_date(child_text(item, ("pubDate", "date", "published")))
        if not title or not link:
            continue
        haystack = f"{title} {summary}".casefold()
        score = sum(8 for keyword in feed.keywords if keyword in haystack)
        score += sum(5 for keyword in PREFERRED if keyword in haystack)
        score -= sum(7 for keyword in DEPRIORITIZED if keyword in haystack)
        score += min(len(summary) // 120, 3)
        items.append(MediaItem(feed.name, title, link, summary, published, score, feed.kind))
    return items


def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"WARN history_invalid path={path}", file=sys.stderr)
        return []
    return data if isinstance(data, list) else []


def save_history(path: Path, history: list[dict]) -> None:
    path.write_text(json.dumps(history[-HISTORY_LIMIT:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def used_links(history: list[dict]) -> set[str]:
    links: set[str] = set()
    for entry in history:
        for key in ("news_link", "listening_link", "review_link"):
            if entry.get(key):
                links.add(str(entry[key]))
    return links


def recent_topics(history: list[dict]) -> set[str]:
    return {str(entry.get("topic", "")).casefold() for entry in history[-20:] if entry.get("topic")}


def next_sequence(history: list[dict]) -> int:
    values = [int(entry.get("sequence", 0)) for entry in history if str(entry.get("sequence", "")).isdigit()]
    return (max(values) if values else 0) + 1


def choose_item(feeds: tuple[Feed, ...], history: list[dict], fallback: MediaItem) -> MediaItem:
    candidates: list[MediaItem] = []
    for feed in feeds:
        candidates.extend(parse_feed(feed))
    fresh = [item for item in candidates if item.link not in used_links(history)]
    pool = fresh or candidates
    if not pool:
        return fallback
    pool.sort(key=lambda item: (item.score, item.published), reverse=True)
    return pool[0]


def choose_scenario(history: list[dict], weekend: bool = False) -> dict:
    topics = recent_topics(history)
    preferred = SCENARIOS[:3] if weekend else SCENARIOS
    for scenario in preferred:
        if scenario["topic"].casefold() not in topics:
            return scenario
    return preferred[len(history) % len(preferred)]


def short_de_summary(item: MediaItem, max_words: int = 120) -> str:
    source = item.summary or item.title
    sentences = re.split(r"(?<=[.!?])\s+", source)
    summary = " ".join(sentences[:3]).strip()
    if len(summary.split()) < 35:
        summary = (
            f"Der Beitrag von {item.source} greift ein aktuelles Thema aus Deutschland auf. "
            "Wichtig ist vor allem, wer betroffen ist, welche Entscheidung oder Entwicklung beschrieben wird "
            "und welche praktische Folge sich im Alltag ergeben könnte."
        )
    return " ".join(summary.split()[:max_words])


def cn_title(item: MediaItem) -> str:
    haystack = f"{item.title} {item.summary}".casefold()
    if "pflege" in haystack:
        return "德国护理/照护相关新闻"
    if "schule" in haystack or "bildung" in haystack:
        return "德国教育/学校相关新闻"
    if "gesundheit" in haystack or "medizin" in haystack:
        return "德国医疗健康相关新闻"
    if "kita" in haystack or "kind" in haystack or "familie" in haystack:
        return "德国育儿和家庭生活相关新闻"
    if "digital" in haystack or "ki" in haystack:
        return "德国科技和数字化相关新闻"
    return "今日德国本土新闻"


def cn_summary(item: MediaItem) -> str:
    return f"这条新闻来自 {item.source}。今天只抓三件事：发生了什么、影响谁、它和德国日常生活有什么关系。"


def fallback_news() -> MediaItem:
    return MediaItem(
        "生活场景兜底",
        "Heute kein stabiler Nachrichtenabruf",
        "https://www.tagesschau.de/",
        "Der Nachrichtenabruf war nicht stabil. Nutze heute den Lebensdialog als Hauptteil und öffne bei Bedarf Tagesschau für eine kurze Inlandsmeldung.",
        "",
        0,
    )


def fallback_listening() -> MediaItem:
    return MediaItem(
        "Tagesschau",
        "Tagesschau in 100 Sekunden",
        "https://www.tagesschau.de/multimedia/sendung/tagesschau_in_100_sekunden/",
        "Kurzer Nachrichtenüberblick in etwa 100 Sekunden. Die Struktur ist klar, die Sprache standardnah und damit gut geeignet, um 70-80 Prozent zu verstehen.",
        "",
        0,
        "video",
    )


def h(text: str) -> str:
    return html.escape(text, quote=True)


def tg(text: str) -> str:
    return html.escape(text, quote=False)


def dialogue_text(dialogue: list[tuple[str, str]], limit: int | None = None) -> str:
    rows = dialogue[:limit] if limit else dialogue
    return "\n".join(f"{speaker}: {line}" for speaker, line in rows)


def expression_rows(expressions: list[tuple[str, str, str, str]]) -> list[dict]:
    return [{"de": de, "cn": cn, "scene": scene, "alt": alt} for de, cn, scene, alt in expressions[:5]]


def helper_sources(news: MediaItem, listening: MediaItem) -> tuple[str, str]:
    news_page = fetch_page_content(news.link)
    listening_page = fetch_page_content(listening.link)
    news_source = " ".join([news.title, news.summary, news_page]).casefold()
    listening_source = " ".join([listening.title, listening.summary, listening_page]).casefold()
    return news_source, listening_source


def matches_helper(item: dict, source: str) -> bool:
    word = item["word"]
    label = helper_label(word)
    probes = {
        word.casefold(),
        label.casefold(),
        word.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").casefold(),
        label.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").casefold(),
    }
    return any(probe in source for probe in probes)


def select_helpers_from_source(source: str, limit: int, seen_roots: set[str] | None = None) -> list[dict]:
    selected: list[dict] = []
    roots = seen_roots if seen_roots is not None else set()
    for item in VOCAB_CANDIDATES:
        word = item["word"]
        root = helper_label(word).split()[0].casefold()
        if root in roots:
            continue
        if matches_helper(item, source):
            selected.append(item | {"source": "page"})
            roots.add(root)
        if len(selected) >= limit:
            return selected
    return selected


def reading_helpers(news: MediaItem, listening: MediaItem) -> tuple[list[dict], list[dict]]:
    news_source, listening_source = helper_sources(news, listening)
    seen_roots: set[str] = set()
    video_helpers = select_helpers_from_source(listening_source, 3, seen_roots)
    news_helpers = select_helpers_from_source(news_source, 5 - len(video_helpers), seen_roots)
    helpers = (video_helpers + news_helpers)[:5]
    if not helpers:
        helpers = select_helpers_from_source(" ".join([news.title, news.summary, listening.title, listening.summary]).casefold(), 5)
    return helpers[:5], video_helpers[:3]


def helper_label(word: str) -> str:
    return word.replace("der ", "").replace("die ", "").replace("das ", "").strip()


def annotate_text(text: str, helpers: list[dict], used: set[str], limit: int = 5) -> str:
    annotated = text
    for item in helpers:
        if len(used) >= limit:
            break
        word = item["word"]
        label = helper_label(word)
        if word in used:
            continue
        pattern = re.compile(rf"\b{re.escape(label)}\b", flags=re.IGNORECASE)
        if not pattern.search(annotated):
            continue

        def replace_once(match: re.Match[str]) -> str:
            return f"{match.group(0)}（{item['cn']}）"

        annotated = pattern.sub(replace_once, annotated, count=1)
        used.add(word)
    return annotated


def helper_list_text(helpers: list[dict]) -> str:
    return "\n".join(f"{helper_label(item['word'])} → {item['cn']}" for item in helpers[:5])


def build_daily(sequence: int, today: dt.date, history: list[dict], mode: str) -> tuple[str, str, str, str, dict]:
    weekend = mode == "saturday"
    scenario = choose_scenario(history, weekend=weekend)
    news = choose_item(NEWS_FEEDS, history, fallback_news())
    listening = choose_item(
        LISTENING_FEEDS,
        history,
        fallback_listening(),
    )
    subject = f"🇩🇪 今日德语 #{sequence:03d} - {today.isoformat()}"
    de_summary = short_de_summary(news, 80)
    expressions = expression_rows(scenario["expressions"])
    vocab, video_vocab = reading_helpers(news, listening)
    card_note = "周六生活场景加强版" if weekend else "第一阶段：生活场景 40% · 听力 40% · 新闻 20%"
    annotated_terms: set[str] = set()
    annotated_dialogue = [
        (speaker, annotate_text(line, vocab, annotated_terms))
        for speaker, line in scenario["dialogue"]
    ]
    annotated_de_summary = annotate_text(de_summary, vocab, annotated_terms)
    annotated_listening_title = annotate_text(listening.title, vocab, annotated_terms)
    video_keywords = helper_list_text(video_vocab or vocab[:3])
    reading_helper = helper_list_text(vocab)

    dialogue_html = "".join(f"<p><strong>{h(speaker)}:</strong> {h(line)}</p>" for speaker, line in annotated_dialogue)
    sentences_html = "".join(f"<li>{h(line)}</li>" for line in scenario["sentences"][:5])
    expr_html = "".join(
        f"<div class='expr'><strong>{h(e['de'])}</strong><br>中文：{h(e['cn'])}<br>场景：{h(e['scene'])}<br>替换：{h(e['alt'])}</div>"
        for e in expressions
    )
    reading_helper_html = "<br>".join(h(line) for line in reading_helper.splitlines())
    video_keywords_html = "<br>".join(h(line) for line in video_keywords.splitlines())

    html_body = html_page(
        subject,
        f"""
<div class="head"><h1>{h(subject)}</h1><p>{h(card_note)}</p></div>
<div class="section card"><h2>🧒 一、今日生活场景，约 4 分钟</h2>
  <p>{h(scenario["intro"])}</p>
  <h3>德语对话</h3><div class="de">{dialogue_html}</div>
  <h3>中文翻译</h3><p>{h(scenario["translation"])}</p>
  <h3>5 个可直接套用句子</h3><ol>{sentences_html}</ol>
</div>
<div class="section card"><h2>🎧 二、今日听力训练，约 3 分钟</h2>
  <h3>视频关键词</h3><p>{video_keywords_html}</p>
  <p><strong>{h(annotated_listening_title)}</strong></p>
  <p><a href="{h(listening.link)}">{h(listening.link)}</a></p>
  <p><strong>德语字幕/文本：</strong>打开页面后优先使用页面自带字幕、文稿或新闻正文。</p>
  <p><strong>中文摘要：</strong>这是一段 1-3 分钟短音频/视频，用来恢复听力反应。目标是听懂 70%-80%，不用逐词听懂。</p>
  <p>推荐理由：短、清楚、信息结构稳定，适合早上先把德语耳朵打开。</p>
</div>
<div class="section card"><h2>📰 三、今日德国新闻，约 2 分钟</h2>
  <h3>德语标题</h3><p class="de">{h(news.title)}</p>
  <h3>中文标题</h3><p>{h(cn_title(news))}</p>
  <h3>德语摘要</h3><p class="de">{h(annotated_de_summary)}</p>
  <h3>中文摘要</h3><p>{h(cn_summary(news))}</p>
  <p><a href="{h(news.link)}">打开原文</a></p>
</div>
<div class="section card"><h2>💬 四、今日表达，约 1 分钟</h2>{expr_html}</div>
<div class="section card"><h2>📖 五、阅读辅助</h2>
  <p>{reading_helper_html}</p>
</div>
""",
    )

    text_body = f"""{subject}

🧒 一、今日生活场景，约 4 分钟
{scenario["intro"]}

德语对话：
{dialogue_text(annotated_dialogue)}

中文翻译：
{scenario["translation"]}

5 个可直接套用句子：
{chr(10).join(f"{i}. {line}" for i, line in enumerate(scenario["sentences"][:5], 1))}

🎧 二、今日听力训练，约 3 分钟
🎧 视频关键词
{video_keywords}

标题：{annotated_listening_title}
链接：{listening.link}
德语字幕/文本：打开页面后优先使用页面自带字幕、文稿或新闻正文。
中文摘要：这是一段 1-3 分钟短音频/视频，用来恢复听力反应。目标是听懂 70%-80%，不用逐词听懂。
推荐理由：短、清楚、信息结构稳定，适合早上先把德语耳朵打开。

📰 三、今日德国新闻，约 2 分钟
德语标题：{news.title}
中文标题：{cn_title(news)}

德语摘要：
{annotated_de_summary}

中文摘要：
{cn_summary(news)}

原文链接：{news.link}

💬 四、今日表达，约 1 分钟
{chr(10).join(f"- {e['de']}\\n  中文：{e['cn']}\\n  场景：{e['scene']}\\n  替换：{e['alt']}" for e in expressions)}

📖 五、阅读辅助
{reading_helper}
"""

    telegram_body = f"""<b>{tg(subject)}</b>

🧒 <b>生活场景</b>
{tg(scenario["intro"])}

<b>德语对话</b>
{tg(dialogue_text(annotated_dialogue))}

<b>中文翻译</b>
{tg(scenario["translation"])}

<b>可直接套用</b>
{tg(chr(10).join(f"{i}. {line}" for i, line in enumerate(scenario["sentences"][:5], 1)))}

🎧 <b>听力训练</b>
<b>视频关键词</b>
{tg(video_keywords)}

{tg(annotated_listening_title)}
{tg(listening.link)}
德语字幕/文本：打开页面后优先使用页面自带字幕、文稿或新闻正文。
中文摘要：1-3 分钟短素材，目标是听懂 70%-80%，不用逐词听懂。

📰 <b>德国新闻</b>
{tg(news.title)}
中文：{tg(cn_title(news))}

{tg(annotated_de_summary)}

{tg(cn_summary(news))}
{tg(news.link)}

💬 <b>今日表达</b>
{tg(chr(10).join(f"- {e['de']}：{e['cn']} / {e['alt']}" for e in expressions))}

📖 <b>阅读辅助</b>
{tg(reading_helper)}
"""

    record = {
        "sequence": sequence,
        "date": today.isoformat(),
        "mode": mode,
        "topic": scenario["topic"],
        "news_title": news.title,
        "news_link": news.link,
        "listening_title": listening.title,
        "listening_link": listening.link,
        "expressions": [e["de"] for e in expressions],
        "vocabulary": [item["word"] for item in vocab],
    }
    return subject, html_body, text_body, telegram_body, record


def build_sunday(sequence: int, today: dt.date, history: list[dict]) -> tuple[str, str, str, str, dict]:
    learned: list[str] = []
    for entry in reversed(history):
        for expr in entry.get("expressions", []):
            if expr not in learned:
                learned.append(expr)
            if len(learned) >= 10:
                break
        if len(learned) >= 10:
            break
    for scenario in SCENARIOS:
        for de, *_ in scenario["expressions"]:
            if de not in learned:
                learned.append(de)
            if len(learned) >= 10:
                break
    learned = learned[:10]
    video = choose_item(
        OPTIONAL_REVIEW_FEEDS,
        history,
        MediaItem("ZDF", "heute journal", "https://www.zdf.de/nachrichten", "Optionales Video unter 20 Minuten.", "", 0, "video"),
    )
    subject = f"🇩🇪 今日德语 #{sequence:03d} - {today.isoformat()}"
    learned_html = "".join(f"<li>{h(expr)}</li>" for expr in learned)
    html_body = html_page(
        subject,
        f"""
<div class="head"><h1>{h(subject)}</h1><p>周日轻量复盘，不强制学习</p></div>
<div class="section card"><h2>💬 本周 10 个重点表达</h2><ol>{learned_html}</ol></div>
<div class="section card"><h2>🧪 3 道小测试</h2>
  <ol><li>用德语描述一次 Kinderarzt 问诊。</li><li>选 3 个表达，各造一个德国生活句子。</li><li>用 60 秒德语复述本周最实用的场景。</li></ol>
</div>
<div class="section card"><h2>🎧 可选 20 分钟以内视频</h2><p><strong>{h(video.title)}</strong></p><p><a href="{h(video.link)}">{h(video.link)}</a></p></div>
""",
    )
    text_body = f"""{subject}

周日轻量复盘

本周 10 个重点表达：
{chr(10).join(f"{i}. {expr}" for i, expr in enumerate(learned, 1))}

3 道小测试：
1. 用德语描述一次 Kinderarzt 问诊。
2. 选 3 个表达，各造一个德国生活句子。
3. 用 60 秒德语复述本周最实用的场景。

可选 20 分钟以内视频：
{video.title}
{video.link}
"""
    telegram_body = f"""<b>{tg(subject)}</b>

💬 <b>本周 10 个重点表达</b>
{tg(chr(10).join(f"{i}. {expr}" for i, expr in enumerate(learned, 1)))}

🧪 <b>3 道小测试</b>
1. 用德语描述一次 Kinderarzt 问诊。
2. 选 3 个表达，各造一个德国生活句子。
3. 用 60 秒德语复述本周最实用的场景。

🎧 <b>可选视频</b>
{tg(video.title)}
{tg(video.link)}
"""
    record = {
        "sequence": sequence,
        "date": today.isoformat(),
        "mode": "sunday",
        "topic": "weekly review",
        "review_title": video.title,
        "review_link": video.link,
        "expressions": learned,
    }
    return subject, html_body, text_body, telegram_body, record


def html_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)}</title>
  <style>
    body {{ margin:0; padding:0; background:#f4f6f8; color:#1f2937; font-family:Arial,"Microsoft YaHei","Noto Sans SC",sans-serif; }}
    .wrap {{ max-width:760px; margin:0 auto; padding:24px 14px; }}
    .mail {{ background:#fff; border:1px solid #e5e7eb; border-radius:8px; overflow:hidden; }}
    .head {{ padding:22px 24px; background:#1f2937; color:#fff; }}
    .head h1 {{ margin:0; font-size:22px; line-height:1.3; }}
    .head p {{ margin:8px 0 0; color:#d1d5db; }}
    .section {{ padding:20px 24px; border-top:1px solid #e5e7eb; }}
    .card {{ background:#fff; }}
    h2 {{ margin:0 0 12px; font-size:18px; color:#111827; }}
    h3 {{ margin:14px 0 6px; font-size:15px; color:#374151; }}
    p {{ line-height:1.65; margin:8px 0; }}
    a {{ color:#0f6abf; word-break:break-word; }}
    ol, ul {{ padding-left:22px; }}
    li {{ margin:7px 0; line-height:1.55; }}
    .de {{ background:#f9fafb; border-left:4px solid #374151; padding:10px 12px; }}
    .expr {{ margin:10px 0; padding:10px 12px; background:#f9fafb; border-radius:6px; }}
  </style>
</head>
<body><div class="wrap"><div class="mail">{body}</div></div></body></html>"""


def resolve_mode(requested: str, today: dt.date) -> str:
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
    parser.add_argument("--html-output", default="deutsch-reaktivierung-email.html")
    parser.add_argument("--text-output", default="deutsch-reaktivierung-email.txt")
    parser.add_argument("--telegram-output", default="deutsch-reaktivierung-telegram.html")
    parser.add_argument("--subject-output", default="deutsch-reaktivierung-subject.txt")
    args = parser.parse_args()

    today = now_berlin().date()
    history_path = Path(args.history)
    history = load_history(history_path)
    sequence = next_sequence(history)
    mode = resolve_mode(args.mode, today)
    if mode == "sunday":
        subject, html_body, text_body, telegram_body, record = build_sunday(sequence, today, history)
    else:
        subject, html_body, text_body, telegram_body, record = build_daily(sequence, today, history, mode)
    history.append(record)
    save_history(history_path, history)
    write_outputs(subject, html_body, text_body, telegram_body, args)

    print(f"Generated mode={mode} subject={subject}")
    if record.get("topic"):
        print(f"Topic: {record['topic']}")
    if record.get("news_title"):
        print(f"News: {record['news_title']}")
    if record.get("listening_title"):
        print(f"Listening: {record['listening_title']}")


if __name__ == "__main__":
    main()
