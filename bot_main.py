import os
import json
import requests
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BAU_CHAT = os.getenv("TELEGRAM_CHAT_ID")
IT_CHAT = os.getenv("TELEGRAM_IT_CHAT_ID")

TED_URL = "https://api.ted.europa.eu/v3/notices/search"
POSTED_FILE = "posted_ids.json"

BAU_KEYWORDS = [
    "construction", "building", "road", "bridge", "railway",
    "renovation", "infrastructure", "civil", "architect",
    "concrete", "roof", "heating", "plumbing",
    "bau", "gebäude", "straße", "brücke", "sanierung",
    "infrastruktur", "architektur", "dach"
]

IT_KEYWORDS = [
    "software", "cloud", "cyber", "digital", "information technology",
    "network", "server", "artificial intelligence", "data",
    "erp", "application", "programming", "cybersecurity",
    "softwareentwicklung", "netzwerk", "digitalisierung",
    "it-dienstleistung"
]


def clean(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        return clean(value[0]) if value else ""

    if isinstance(value, dict):
        for key in ["deu", "de", "eng", "en"]:
            if key in value:
                return clean(value[key])

        if value:
            return clean(next(iter(value.values())))

    return str(value)


try:
    with open(POSTED_FILE, "r", encoding="utf-8") as file:
        posted_ids = set(json.load(file))
except (FileNotFoundError, json.JSONDecodeError):
    posted_ids = set()


today = datetime.now(timezone.utc).strftime("%Y%m%d")


payload = {
    "query": f"place-of-performance = DEU AND publication-date = {today}",
    "fields": [
        "publication-number",
        "notice-title",
        "buyer-name",
        "publication-date"
    ],
    "limit": 50,
    "page": 1,
    "paginationMode": "PAGE_NUMBER"
}


response = requests.post(
    TED_URL,
    json=payload,
    timeout=30
)

response.raise_for_status()

data = response.json()
notices = data.get("notices", [])

telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

new_posted_ids = set()


for notice in notices:

    title = clean(notice.get("notice-title"))
    buyer = clean(notice.get("buyer-name"))
    number = clean(notice.get("publication-number"))
    date = clean(notice.get("publication-date"))

    if not number or number in posted_ids:
        continue

    searchable_text = f"{title} {buyer}".lower()

    chat = None

    if any(keyword in searchable_text for keyword in BAU_KEYWORDS):
        chat = BAU_CHAT

    elif any(keyword in searchable_text for keyword in IT_KEYWORDS):
        chat = IT_CHAT

    if chat is None:
        continue

    message = (
        "🚨 Neue Ausschreibung\n\n"
        f"📌 {title[:700]}\n\n"
        f"🏢 Auftraggeber:\n{buyer[:250]}\n\n"
        f"📅 Veröffentlicht: {date}\n"
        f"🔢 Nummer: {number}\n\n"
        "🔗 Ausschreibung öffnen:\n"
        f"https://ted.europa.eu/de/notice/-/detail/{number}"
    )

    telegram_response = requests.post(
        telegram_url,
        data={
            "chat_id": chat,
            "text": message
        },
        timeout=30
    )

    telegram_data = telegram_response.json()

    if telegram_data.get("ok") is True:
        new_posted_ids.add(number)
        print(f"Erfolgreich gepostet: {number}")
    else:
        print(f"Telegram-Fehler bei {number}: {telegram_data}")


posted_ids.update(new_posted_ids)

with open(POSTED_FILE, "w", encoding="utf-8") as file:
    json.dump(
        sorted(posted_ids),
        file,
        ensure_ascii=False,
        indent=2
    )

print(f"Neue Ausschreibungen gepostet: {len(new_posted_ids)}")
