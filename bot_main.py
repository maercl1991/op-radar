import os
import io
import re
import json
import hashlib
import zipfile
import requests
from datetime import datetime
from zoneinfo import ZoneInfo


# ============================================================
# EINSTELLUNGEN
# ============================================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

BAU_CHAT = os.getenv("TELEGRAM_CHAT_ID")
IT_CHAT = os.getenv("TELEGRAM_IT_CHAT_ID")

POSTED_FILE = "posted_ids.json"

TED_URL = "https://api.ted.europa.eu/v3/notices/search"

OE_URL = "https://oeffentlichevergabe.de/api/notice-exports"


# CPV:
# 45 = Bauarbeiten
# 48 = Software / Informationssysteme
# 72 = IT-Dienstleistungen

BAU_PREFIXES = ("45",)
IT_PREFIXES = ("48", "72")


# ============================================================
# ALLGEMEINE HILFSFUNKTIONEN
# ============================================================

def clean_text(value):
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

        for key in ["deu", "de", "DE"]:
            if key in value:
                text = clean_text(value[key])
                if text:
                    return text

        for key in ["eng", "en", "EN"]:
            if key in value:
                text = clean_text(value[key])
                if text:
                    return text

        for item in value.values():
            text = clean_text(item)
            if text:
                return text

    return str(value).strip()


def extract_cpv_codes(value):
    codes = set()

    if value is None:
        return codes

    if isinstance(value, dict):

        # Häufig steht der CPV-Code direkt unter "id"
        if "id" in value:
            candidate = str(value["id"])
            match = re.search(r"(\d{8})", candidate)

            if match:
                codes.add(match.group(1))

        for item in value.values():
            codes.update(extract_cpv_codes(item))

    elif isinstance(value, list):

        for item in value:
            codes.update(extract_cpv_codes(item))

    else:

        matches = re.findall(
            r"(?<!\d)(\d{8})(?!\d)",
            str(value)
        )

        codes.update(matches)

    return codes


def classify_cpv(codes):

    has_bau = any(
        code.startswith(BAU_PREFIXES)
        for code in codes
    )

    has_it = any(
        code.startswith(IT_PREFIXES)
        for code in codes
    )

    # Wir posten nur eindeutige Treffer.
    if has_bau and not has_it:
        return "bau"

    if has_it and not has_bau:
        return "it"

    return None


def normalize(text):

    text = text.lower()

    text = re.sub(
        r"[^a-zäöüß0-9]+",
        " ",
        text
    )

    return " ".join(
        text.split()
    )


def create_fingerprint(title, buyer):

    raw = (
        normalize(title)
        + "|"
        + normalize(buyer)
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def send_telegram(chat_id, message):

    if not chat_id:
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    try:

        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": message,
                "disable_web_page_preview": True
            },
            timeout=30
        )

        result = response.json()

        if result.get("ok") is True:
            return True

        print("Telegram Fehler:")
        print(result)

    except Exception as error:

        print(
            "Telegram-Verbindungsfehler:",
            error
        )

    return False


# ============================================================
# GEDÄCHTNIS LADEN
# ============================================================

try:

    with open(
        POSTED_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        saved = json.load(file)

        if isinstance(saved, list):
            posted_ids = set(saved)

        else:
            posted_ids = set()

except (
    FileNotFoundError,
    json.JSONDecodeError
):

    posted_ids = set()


new_posted_ids = set()


# ============================================================
# HEUTIGES DATUM
# ============================================================

berlin_now = datetime.now(
    ZoneInfo("Europe/Berlin")
)

today_ted = berlin_now.strftime(
    "%Y%m%d"
)

today_oe = berlin_now.strftime(
    "%Y-%m-%d"
)


# ============================================================
# GEMEINSAME VERARBEITUNG
# ============================================================

def process_notice(
    title,
    buyer,
    number,
    publication_date,
    cpv_codes,
    link,
    source
):

    title = clean_text(title)
    buyer = clean_text(buyer)
    number = clean_text(number)

    if not title:
        title = "Titel nicht angegeben"

    if not buyer:
        buyer = "Auftraggeber nicht angegeben"

    category = classify_cpv(
        cpv_codes
    )

    if category is None:
        return

    # --------------------------------------------------------
    # QUELLENÜBERGREIFENDE DUPLIKAT-ERKENNUNG
    # --------------------------------------------------------

    fingerprint = create_fingerprint(
        title,
        buyer
    )

    fingerprint_key = (
        "FP:" + fingerprint
    )

    source_key = (
        source
        + ":"
        + number
    )

    if (
        fingerprint_key in posted_ids
        or fingerprint_key in new_posted_ids
        or source_key in posted_ids
        or source_key in new_posted_ids
    ):
        return


    if category == "bau":

        chat_id = BAU_CHAT

        category_name = (
            "🏗 Bau & Infrastruktur"
        )

    else:

        chat_id = IT_CHAT

        category_name = (
            "💻 IT, Software & Digitalisierung"
        )


    cpv_display = ", ".join(
        sorted(cpv_codes)
    )

    if not cpv_display:
        cpv_display = "Keine Angabe"


    message = (
        "🚨 NEUE AUSSCHREIBUNG\n\n"

        f"{category_name}\n\n"

        f"📌 {title[:900]}\n\n"

        "🏢 Auftraggeber:\n"
        f"{buyer[:400]}\n\n"

        f"📅 Veröffentlicht: "
        f"{publication_date}\n\n"

        f"🏷 CPV: {cpv_display}\n"

        f"🔢 Nummer: "
        f"{number}\n\n"

        f"📡 Quelle: "
        f"{source}\n\n"

        "🔗 Ausschreibung öffnen:\n"
        f"{link}"
    )


    success = send_telegram(
        chat_id,
        message
    )


    if success:

        new_posted_ids.add(
            fingerprint_key
        )

        new_posted_ids.add(
            source_key
        )

        print(
            f"✅ {source} / "
            f"{category.upper()} "
            f"gepostet: {number}"
        )


# ============================================================
# QUELLE 1: TED
# ============================================================

def fetch_ted():

    print("TED wird geprüft...")

    payload = {

        "query":
            f"place-of-performance = DEU "
            f"AND publication-date = "
            f"{today_ted}",

        "fields": [
            "publication-number",
            "notice-title",
            "buyer-name",
            "publication-date",
            "main-classification-proc",
            "main-classification-lot",
            "classification-cpv"
        ],

        "page": 1,

        "limit": 100,

        "paginationMode":
            "PAGE_NUMBER"
    }


    response = requests.post(
        TED_URL,
        json=payload,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    notices = data.get(
        "notices",
        []
    )

    print(
        "TED Treffer:",
        len(notices)
    )


    for notice in notices:

        number = clean_text(
            notice.get(
                "publication-number"
            )
        )

        title = clean_text(
            notice.get(
                "notice-title"
            )
        )

        buyer = clean_text(
            notice.get(
                "buyer-name"
            )
        )

        publication_date = clean_text(
            notice.get(
                "publication-date"
            )
        )


        cpv_codes = set()

        cpv_codes.update(
            extract_cpv_codes(
                notice.get(
                    "main-classification-proc"
                )
            )
        )

        cpv_codes.update(
            extract_cpv_codes(
                notice.get(
                    "main-classification-lot"
                )
            )
        )

        cpv_codes.update(
            extract_cpv_codes(
                notice.get(
                    "classification-cpv"
                )
            )
        )


        link = (
            "https://ted.europa.eu/"
            "de/notice/-/detail/"
            + number
        )


        process_notice(
            title=title,
            buyer=buyer,
            number=number,
            publication_date=publication_date,
            cpv_codes=cpv_codes,
            link=link,
            source="TED"
        )


# ============================================================
# QUELLE 2: ÖFFENTLICHEVERGABE.DE
# ============================================================

def find_buyer_from_ocds(
    release
):

    buyer_name = ""

    buyer = release.get(
        "buyer",
        {}
    )

    if isinstance(
        buyer,
        dict
    ):

        buyer_name = clean_text(
            buyer.get("name")
        )

    if buyer_name:
        return buyer_name


    # Fallback über OCDS-Parties

    parties = release.get(
        "parties",
        []
    )

    for party in parties:

        roles = party.get(
            "roles",
            []
        )

        if "buyer" in roles:

            name = clean_text(
                party.get("name")
            )

            if name:
                return name

    return ""


def find_cpv_from_ocds(
    tender
):

    codes = set()

    classification = tender.get(
        "classification"
    )

    codes.update(
        extract_cpv_codes(
            classification
        )
    )

    additional = tender.get(
        "additionalClassifications",
        []
    )

    codes.update(
        extract_cpv_codes(
            additional
        )
    )


    # Lose ebenfalls berücksichtigen

    lots = tender.get(
        "lots",
        []
    )

    for lot in lots:

        codes.update(
            extract_cpv_codes(
                lot.get(
                    "classification"
                )
            )
        )

        codes.update(
            extract_cpv_codes(
                lot.get(
                    "additionalClassifications",
                    []
                )
            )
        )

    return codes


def fetch_oeffentliche_vergabe():

    print(
        "ÖffentlicheVergabe.de "
        "wird geprüft..."
    )


    response = requests.get(
        OE_URL,
        params={
            "pubDay": today_oe,
            "format": "ocds.zip"
        },
        timeout=120
    )

    response.raise_for_status()


    archive = zipfile.ZipFile(
        io.BytesIO(
            response.content
        )
    )


    files = archive.namelist()

    print(
        "ÖffentlicheVergabe "
        "Dateien:",
        len(files)
    )


    for filename in files:

        if not filename.lower().endswith(
            ".json"
        ):
            continue


        try:

            raw = archive.read(
                filename
            )

            package = json.loads(
                raw.decode(
                    "utf-8"
                )
            )

        except Exception as error:

            print(
                "Datei konnte nicht "
                "gelesen werden:",
                filename,
                error
            )

            continue


        releases = package.get(
            "releases",
            []
        )


        for release in releases:

            tender = release.get(
                "tender",
                {}
            )

            title = clean_text(
                tender.get(
                    "title"
                )
            )


            buyer = find_buyer_from_ocds(
                release
            )


            # OCDS-ID als eindeutige Nummer

            number = clean_text(
                release.get(
                    "id"
                )
            )

            if not number:

                number = clean_text(
                    release.get(
                        "ocid"
                    )
                )


            publication_date = clean_text(
                release.get(
                    "date"
                )
            )


            cpv_codes = (
                find_cpv_from_ocds(
                    tender
                )
            )


            # noticeId aus dem Dateinamen
            notice_id = (
                filename
                .split("/")[-1]
                .split(".json")[0]
            )

            # Bei Versionssuffix versuchen,
            # den UUID-Teil zu verwenden.
            uuid_match = re.search(
                r"([0-9a-fA-F]{8}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{12})",
                notice_id
            )

            if uuid_match:

                notice_id = (
                    uuid_match.group(1)
                )


            link = (
                "https://"
                "oeffentlichevergabe.de/"
                "ui/de/search/details"
                "?noticeId="
                + notice_id
            )


            process_notice(
                title=title,
                buyer=buyer,
                number=number,
                publication_date=publication_date,
                cpv_codes=cpv_codes,
                link=link,
                source="ÖffentlicheVergabe.de"
            )


# ============================================================
# BEIDE QUELLEN AUSFÜHREN
# ============================================================

try:

    fetch_ted()

except Exception as error:

    # Wichtig:
    # Wenn TED ausfällt, soll Quelle 2
    # trotzdem funktionieren.

    print(
        "❌ TED Fehler:",
        error
    )


try:

    fetch_oeffentliche_vergabe()

except Exception as error:

    # Auch umgekehrt:
    # TED läuft weiter, wenn diese
    # Quelle einmal Probleme hat.

    print(
        "❌ ÖffentlicheVergabe "
        "Fehler:",
        error
    )


# ============================================================
# GEDÄCHTNIS SPEICHERN
# ============================================================

posted_ids.update(
    new_posted_ids
)


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
    "✅ Lauf abgeschlossen."
)

print(
    "Neue Einträge gespeichert:",
    len(new_posted_ids)
)
