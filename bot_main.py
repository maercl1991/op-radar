import os
import requests

token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

def clean_text(value):
    """Holt einen lesbaren Text aus TED-Feldern."""
    
    if value is None:
        return "Keine Angabe"

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        if not value:
            return "Keine Angabe"
        return clean_text(value[0])

    if isinstance(value, dict):
        # Deutsch bevorzugen
        for key in ["deu", "de", "DE"]:
            if key in value:
                return clean_text(value[key])

        # Danach Englisch
        for key in ["eng", "en", "EN"]:
            if key in value:
                return clean_text(value[key])

        # Falls weder Deutsch noch Englisch vorhanden ist:
        # ersten verfügbaren Text nehmen
        for item in value.values():
            text = clean_text(item)
            if text != "Keine Angabe":
                return text

    return str(value)


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

response = requests.post(
    ted_url,
    json=payload,
    timeout=30
)

response.raise_for_status()

data = response.json()
notices = data.get("notices", [])

telegram_url = f"https://api.telegram.org/bot{token}/sendMessage"

if not notices:

    requests.post(
        telegram_url,
        data={
            "chat_id": chat_id,
            "text": "🔎 Aktuell wurden keine passenden Ausschreibungen gefunden."
        },
        timeout=30
    )

else:

    for notice in notices:

        publication_number = clean_text(
            notice.get("publication-number")
        )

        title = clean_text(
            notice.get("notice-title")
        )

        buyer = clean_text(
            notice.get("buyer-name")
        )

        publication_date = clean_text(
            notice.get("publication-date")
        )

        # Telegram-Sicherheitslimit
        title = title[:700]
        buyer = buyer[:300]

        message = (
            "🚨 NEUE AUSSCHREIBUNG\n\n"
            f"📌 {title}\n\n"
            f"🏢 Auftraggeber:\n{buyer}\n\n"
            f"📅 Veröffentlicht: {publication_date}\n"
            f"🔢 Nummer: {publication_number}\n\n"
            "🔗 Ausschreibung öffnen:\n"
            f"https://ted.europa.eu/de/notice/-/detail/{publication_number}"
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
