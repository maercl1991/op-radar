import os
import requests

token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

ted_url = "https://api.ted.europa.eu/v3/notices/search"

payload = {
    "query": "place-of-performance = DEU",
    "fields": [
        "publication-number",
        "notice-title",
        "buyer-name",
        "publication-date"
    ],
    "page": 1,
    "limit": 5,
    "paginationMode": "PAGE_NUMBER"
}

response = requests.post(ted_url, json=payload, timeout=30)
response.raise_for_status()

data = response.json()
notices = data.get("notices", [])

telegram_url = f"https://api.telegram.org/bot{token}/sendMessage"

if not notices:
    requests.post(
        telegram_url,
        data={
            "chat_id": chat_id,
            "text": "🔎 Opportunity Radar: Aktuell wurden keine passenden Ausschreibungen gefunden."
        },
        timeout=30
    )

else:
    for notice in notices:
        publication_number = str(
            notice.get("publication-number", "Keine Nummer")
        )

        title = str(
            notice.get("notice-title", "Kein Titel")
        )

        buyer = str(
            notice.get("buyer-name", "Unbekannter Auftraggeber")
        )

        # Sicherheitslimit, damit Telegram-Nachrichten nicht zu lang werden
        title = title[:800]
        buyer = buyer[:500]

        message = (
            f"🚨 Neue Ausschreibung\n\n"
            f"📌 {title}\n\n"
            f"🏢 {buyer}\n"
            f"🔢 {publication_number}\n\n"
            f"🔗 https://ted.europa.eu/de/notice/-/detail/{publication_number}"
        )

        telegram_response = requests.post(
            telegram_url,
            data={
                "chat_id": chat_id,
                "text": message
            },
            timeout=30
        )

        print(telegram_response.text)
