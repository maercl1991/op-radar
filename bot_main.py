import os
import json
import re
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# --------------------------------------------------
# EINSTELLUNGEN
# --------------------------------------------------

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BAU_CHAT = os.getenv("TELEGRAM_CHAT_ID")
IT_CHAT = os.getenv("TELEGRAM_IT_CHAT_ID")

TED_URL = "https://api.ted.europa.eu/v3/notices/search"
POSTED_FILE = "posted_ids.json"

# Offizielle CPV-Hauptbereiche:
# 45 = Bauarbeiten
# 48 = Softwarepakete und Informationssysteme
# 72 = IT-Dienstleistungen

BAU_PREFIXES = ("45",)
IT_PREFIXES = ("48", "72")


# --------------------------------------------------
# HILFSFUNKTIONEN
# --------------------------------------------------

def clean_text(value):
    """Macht TED-Felder zu sauber lesbarem Text."""

    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        for item in value:
            text = clean_text(item)
            if text:
                return text
        return ""

    if isinstance(value, dict):

        # Deutsch bevorzugen
        for key in ["deu", "de", "DE"]:
            if key in value:
                text = clean_text(value[key])
                if text:
                    return text

        # Danach Englisch
        for key in ["eng", "en", "EN"]:
            if key in value:
                text = clean_text(value[key])
                if text:
                    return text

        # Sonst ersten brauchbaren Wert nehmen
        for item in value.values():
            text = clean_text(item)
            if text:
                return text

    return str(value).strip()


def extract_cpv_codes(value):
    """
    Sucht rekursiv nach achtstelligen CPV-Codes.
    Funktioniert auch bei Listen, Dictionaries oder URLs.
    """

    codes = set()

    if value is None:
        return codes

    if isinstance(value, dict):
        for item in value.values():
            codes.update(extract_cpv_codes(item))

    elif isinstance(value, list):
        for item in value:
            codes.update(extract_cpv_codes(item))

    else:
        text = str(value)

        # CPV-Codes haben 8 Ziffern
        matches = re.findall(r"(?<!\d)(\d{8})(?!\d)", text)

        for match in matches:
            codes.add(match)

    return codes


def determine_category(notice):
    """
    Verwendet möglichst die HAUPT-CPV-Klassifikation.
    Dadurch reicht ein zufälliges IT-Wort im Text nicht mehr aus.
    """

    # 1. Hauptklassifikation des gesamten Verfahrens bevorzugen
    procedure_codes = extract_cpv_codes(
        notice.get("main-classification-proc")
    )

    if procedure_codes:
        codes = procedure_codes

    else:
        # 2. Falls nicht vorhanden: Hauptklassifikation der Lose
        lot_codes = extract_cpv_codes(
            notice.get("main-classification-lot")
        )

        if lot_codes:
            codes = lot_codes

        else:
            # 3. Letzte Rückfallebene
            codes = extract_cpv_codes(
                notice.get("classification-cpv")
            )

    has_bau = any(
        code.startswith(BAU_PREFIXES)
        for code in codes
    )

    has_it = any(
        code.startswith(IT_PREFIXES)
        for code in codes
    )

    # Wenn ausschließlich Bau:
    if has_bau and not has_it:
        return "bau", codes

    # Wenn ausschließlich IT:
    if has_it and not has_bau:
        return "it", codes

    # Wenn Hauptcodes beides enthalten oder nichts eindeutig ist:
    # lieber NICHT posten als falsch einsortieren.
    return None, codes


def send_telegram(chat_id, message):
    """Sendet eine Nachricht und gibt True bei Erfolg zurück."""

    telegram_url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        telegram_url,
        data={
            "chat_id": chat_id,
            "text": message
        },
        timeout=30
    )

    try:
        result = response.json()
    except Exception:
        print("Telegram-Antwort konnte nicht gelesen werden.")
        print(response.text)
        return False

    if result.get("ok") is True:
        return True

    print("Telegram-Fehler:")
    print(result)

    return False


# --------------------------------------------------
# BEREITS GEPOSTETE AUSSCHREIBUNGEN LADEN
# --------------------------------------------------

try:
    with open(POSTED_FILE, "r", encoding="utf-8") as file:
        posted_ids = set(json.load(file))

except (FileNotFoundError, json.JSONDecodeError):
    posted_ids = set()


# --------------------------------------------------
# NUR HEUTIGES DATUM – DEUTSCHE ZEIT
# --------------------------------------------------

today = datetime.now(
    ZoneInfo("Europe/Berlin")
).strftime("%Y%m%d")


# --------------------------------------------------
# TED ABFRAGEN
# --------------------------------------------------

payload = {

    "query":
        f"place-of-performance = DEU "
        f"AND publication-date = {today}",

    "fields": [
        "publication-number",
        "notice-title",
        "buyer-name",
        "publication-date",

        # Für unsere neue CPV-Erkennung:
        "main-classification-proc",
        "main-classification-lot",
        "classification-cpv"
    ],

    "page": 1,

    # Erstmal bis zu 100 heutige Treffer prüfen
    "limit": 100,

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

print(
    f"Heutige TED-Treffer gefunden: {len(notices)}"
)


# --------------------------------------------------
# AUSSCHREIBUNGEN VERARBEITEN
# --------------------------------------------------

new_posted_ids = set()


for notice in notices:

    number = clean_text(
        notice.get("publication-number")
    )

    # Keine Nummer = nicht verwendbar
    if not number:
        continue

    # Schon einmal veröffentlicht?
    if number in posted_ids:
        continue

    category, cpv_codes = determine_category(notice)

    # Weder eindeutig Bau noch eindeutig IT
    if category is None:
        continue

    title = clean_text(
        notice.get("notice-title")
    )

    buyer = clean_text(
        notice.get("buyer-name")
    )

    publication_date = clean_text(
        notice.get("publication-date")
    )

    cpv_display = ", ".join(
        sorted(cpv_codes)
    )

    if not title:
        title = "Titel nicht angegeben"

    if not buyer:
        buyer = "Auftraggeber nicht angegeben"


    # --------------------------------------------------
    # RICHTIGEN TELEGRAM-KANAL AUSWÄHLEN
    # --------------------------------------------------

    if category == "bau":

        chat_id = BAU_CHAT
        category_name = "🏗 Bau & Infrastruktur"

    elif category == "it":

        chat_id = IT_CHAT
        category_name = "💻 IT, Software & Digitalisierung"

    else:
        continue


    # --------------------------------------------------
    # NACHRICHT ERSTELLEN
    # --------------------------------------------------

    message = (
        f"🚨 NEUE AUSSCHREIBUNG\n\n"
        f"{category_name}\n\n"

        f"📌 {title[:900]}\n\n"

        f"🏢 Auftraggeber:\n"
        f"{buyer[:400]}\n\n"

        f"📅 Veröffentlicht: "
        f"{publication_date}\n\n"

        f"🏷 CPV: {cpv_display}\n"

        f"🔢 Nummer: {number}\n\n"

        f"🔗 Ausschreibung öffnen:\n"
        f"https://ted.europa.eu/de/notice/-/detail/{number}"
    )


    # --------------------------------------------------
    # TELEGRAM SENDEN
    # --------------------------------------------------

    success = send_telegram(
        chat_id,
        message
    )

    # Nur merken, wenn Telegram wirklich erfolgreich war
    if success:

        new_posted_ids.add(number)

        print(
            f"✅ {category.upper()} gepostet: "
            f"{number}"
        )


# --------------------------------------------------
# GEDÄCHTNIS AKTUALISIEREN
# --------------------------------------------------

posted_ids.update(new_posted_ids)

with open(
    POSTED_FILE,
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        sorted(posted_ids),
        file,
        ensure_ascii=False,
        indent=2
    )


print(
    f"Neue Ausschreibungen gepostet: "
    f"{len(new_posted_ids)}"
)
