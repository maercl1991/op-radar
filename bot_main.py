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

if not notices:
    message = "🔎 Opportunity Radar: Aktuell wurden keine passenden Ausschreibungen gefunden."
else:
    message = "🚨 Neue Ausschreibungen gefunden:\n\n"

    for notice in notices:
        publication_number = notice.get("publication-number", "Keine Nummer")
        title = notice.get("notice-title", "Kein Titel")
        buyer = notice.get("buyer-name", "Unbekannter Auftraggeber")

        message += (
            f"📌 {title}\n"
            f"🏢 {buyer}\n"
            f"🔢 {publication_number}\n"
            f"🔗 https://ted.europa.eu/de/notice/-/detail/{publication_number}\n\n"
        )

telegram_url = f"https://api.telegram.org/bot{token}/sendMessage"

telegram_response = requests.post(
    telegram_url,
    data={
        "chat_id": chat_id,
        "text": message
    },
    timeout=30
)

print(telegram_response.text)
