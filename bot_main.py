import os
import requests
from datetime import datetime

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BAU_CHAT = os.getenv("TELEGRAM_CHAT_ID")
IT_CHAT = os.getenv("TELEGRAM_IT_CHAT_ID")

TED_URL = "https://api.ted.europa.eu/v3/notices/search"

# Wörter zur Erkennung der Nischen
BAU_KEYWORDS = [
    "construction", "building", "road", "bridge", "railway",
    "renovation", "infrastructure", "civil", "architect",
    "concrete", "roof", "heating", "plumbing"
]

IT_KEYWORDS = [
    "software", "cloud", "cyber", "digital", "it ",
    "network", "server", "ai", "data", "erp",
    "application", "programming", "security"
]


def clean(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return clean(value[0]) if value else ""
    if isinstance(value, dict):
        for k in ["deu", "de", "eng", "en"]:
            if k in value:
                return clean(value[k])
        return clean(next(iter(value.values())))
    return str(value)


today = datetime.utcnow().strftime("%Y-%m-%d")

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

response = requests.post(TED_URL, json=payload, timeout=30)
response.raise_for_status()

data = response.json()
notices = data.get("notices", [])

telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

for notice in notices:

    title = clean(notice.get("notice-title"))
    buyer = clean(notice.get("buyer-name"))
    number = clean(notice.get("publication-number"))
    date = clean(notice.get("publication-date"))

    text = f"{title} {buyer}".lower()

    chat = None

    if any(k in text for k in BAU_KEYWORDS):
        chat = BAU_CHAT

    elif any(k in text for k in IT_KEYWORDS):
        chat = IT_CHAT

    if chat is None:
        continue

    message = (
        "🚨 Neue Ausschreibung\n\n"
        f"📌 {title[:700]}\n\n"
        f"🏢 {buyer[:250]}\n\n"
        f"📅 {date}\n"
        f"🔢 {number}\n\n"
        f"https://ted.europa.eu/de/notice/-/detail/{number}"
    )

    requests.post(
        telegram_url,
        data={
            "chat_id": chat,
            "text": message
        },
        timeout=30
    )
