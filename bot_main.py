import os
import io
import re
import json
import hashlib
import zipfile
import requests

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ============================================================
# EINSTELLUNGEN
# ============================================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

BAU_CHAT = os.getenv("TELEGRAM_CHAT_ID")
IT_CHAT = os.getenv("TELEGRAM_IT_CHAT_ID")

POSTED_FILE = "posted_ids.json"
PROFILE_FILE = "company_profile.json"

TED_URL = "https://api.ted.europa.eu/v3/notices/search"

OE_EXPORT_URL = (
    "https://oeffentlichevergabe.de/api/notice-exports"
)

BAU_PREFIXES = ("45",)
IT_PREFIXES = ("48", "72")


# ============================================================
# ELEKTRO-CPV FÜR UNSER TESTPROFIL
# ============================================================

ELECTRO_CPV_PREFIXES = (
    "45310",
    "45311",
    "45312",
    "45314",
    "45315",
    "45316",
    "45317"
)

ELECTRO_CPV_EXCLUDED_PREFIXES = (
    "45313",   # Aufzüge / Rolltreppen
    "453154",  # Hochspannung
    "453155"   # Mittelspannung
)


# ============================================================
# COMPANY DNA LADEN
# ============================================================

with open(
    PROFILE_FILE,
    "r",
    encoding="utf-8"
) as file:

    COMPANY_PROFILE = json.load(file)


MINIMUM_MATCH_SCORE = (
    COMPANY_PROFILE
    .get("matching", {})
    .get("minimum_match_score", 70)
)


# ============================================================
# SERVICE-ALIASE
# ============================================================

SERVICE_ALIASES = [
    "elektro",
    "elektrik",
    "elektrisch",
    "elektrotechnik",
    "elektroinstallation",
    "elektroarbeiten",
    "elektroanlage",
    "elektroanlagen",
    "starkstrom",
    "schwachstrom",
    "niederspannung",
    "niederspannungsanlage",
    "beleuchtungsanlage",
    "beleuchtungstechnik",
    "sicherheitsbeleuchtung",
    "notbeleuchtung",
    "schaltschrank",
    "schaltschränke",
    "gebäudeautomation",
    "gebäudetechnik",
    "datennetz",
    "datennetzwerk",
    "netzwerktechnik",
    "fernmeldeanlage",
    "brandmeldeanlage",
    "bma",
    "elektrische installation"
]


FOREIGN_WORK_KEYWORDS = [
    "brückenbau",
    "brücke",
    "kanalbau",
    "kanalsanierung",
    "straßenbau",
    "straßensanierung",
    "asphaltarbeiten",
    "erdarbeiten",
    "tiefbau",
    "gleisbau",
    "rohrleitungsbau",
    "betonbau",
    "mauerarbeiten",
    "zimmerarbeiten",
    "dachdeckerarbeiten",
    "abbrucharbeiten",
    "bodenbelagarbeiten",
    "fassadensanierung",
    "regenentwässerung",
    "außenanlagen"
]


# ============================================================
# HILFSFUNKTIONEN
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

                text = clean_text(
                    value[key]
                )

                if text:
                    return text

        for key in ["eng", "en", "EN"]:

            if key in value:

                text = clean_text(
                    value[key]
                )

                if text:
                    return text

        for item in value.values():

            text = clean_text(item)

            if text:
                return text

    return str(value).strip()


def normalize(text):

    text = clean_text(text).lower()

    text = re.sub(
        r"[^a-zäöüß0-9]+",
        " ",
        text
    )

    return " ".join(
        text.split()
    )


def extract_number(value):

    if value is None:
        return None

    if isinstance(value, list):

        for item in value:

            result = extract_number(item)

            if result is not None:
                return result

        return None

    if isinstance(value, dict):

        for key in [
            "amount",
            "value",
            "estimatedValue"
        ]:

            if key in value:

                result = extract_number(
                    value[key]
                )

                if result is not None:
                    return result

        for item in value.values():

            result = extract_number(item)

            if result is not None:
                return result

        return None

    try:

        return float(value)

    except Exception:

        text = str(value)

        match = re.search(
            r"\d+(?:[.,]\d+)?",
            text
        )

        if match:

            try:

                return float(
                    match
                    .group(0)
                    .replace(",", ".")
                )

            except Exception:

                return None

    return None


def extract_cpv_codes(value):

    codes = set()

    if value is None:
        return codes

    if isinstance(value, dict):

        if "id" in value:

            candidate = str(
                value["id"]
            )

            match = re.search(
                r"(\d{8})",
                candidate
            )

            if match:

                codes.add(
                    match.group(1)
                )

        for item in value.values():

            codes.update(
                extract_cpv_codes(item)
            )

    elif isinstance(value, list):

        for item in value:

            codes.update(
                extract_cpv_codes(item)
            )

    else:

        matches = re.findall(
            r"(?<!\d)(\d{8})(?!\d)",
            str(value)
        )

        codes.update(matches)

    return codes


def classify_cpv(codes):

    has_bau = any(
        code.startswith(
            BAU_PREFIXES
        )
        for code in codes
    )

    has_it = any(
        code.startswith(
            IT_PREFIXES
        )
        for code in codes
    )

    if has_bau and not has_it:
        return "bau"

    if has_it and not has_bau:
        return "it"

    return None


def has_relevant_electro_cpv(codes):

    for code in codes:

        if code.startswith(
            ELECTRO_CPV_EXCLUDED_PREFIXES
        ):
            continue

        if code.startswith(
            ELECTRO_CPV_PREFIXES
        ):
            return True

    return False


def has_excluded_electro_cpv(codes):

    return any(
        code.startswith(
            ELECTRO_CPV_EXCLUDED_PREFIXES
        )
        for code in codes
    )


def create_fingerprint(
    title,
    buyer
):

    raw = (
        normalize(title)
        + "|"
        + normalize(buyer)
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def contains_any(
    text,
    keywords
):

    text = normalize(text)

    for keyword in keywords:

        normalized_keyword = normalize(
            keyword
        )

        if (
            normalized_keyword
            and
            normalized_keyword in text
        ):
            return True

    return False


def matching_keywords(
    text,
    keywords
):

    text = normalize(text)

    matches = []

    for keyword in keywords:

        normalized_keyword = normalize(
            keyword
        )

        if (
            normalized_keyword
            and
            normalized_keyword in text
        ):

            matches.append(
                keyword
            )

    return matches


# ============================================================
# MATCHING V3
# ============================================================

def calculate_match(
    title,
    buyer,
    location_text,
    contract_value,
    cpv_codes,
    description=""
):

    profile = COMPANY_PROFILE

    title_text = normalize(
        title
    )

    description_text = normalize(
        description
    )


    service_terms = list(
        profile.get(
            "services",
            []
        )
    )

    service_terms.extend(
        SERVICE_ALIASES
    )


    title_service_matches = matching_keywords(
        title_text,
        service_terms
    )


    description_service_matches = matching_keywords(
        description_text,
        service_terms
    )


    electro_cpv_match = (
        has_relevant_electro_cpv(
            cpv_codes
        )
    )


    excluded_cpv = (
        has_excluded_electro_cpv(
            cpv_codes
        )
    )


    foreign_title_matches = matching_keywords(
        title_text,
        FOREIGN_WORK_KEYWORDS
    )


    # ========================================================
    # K.O. – ausgeschlossener Elektrobereich
    # ========================================================

    if excluded_cpv:

        return {
            "eligible": False,
            "score": 0,
            "confidence": 100,
            "ko": True,
            "reasons": [
                "✗ CPV-Hauptleistung passt nicht zum Unternehmensprofil"
            ],
            "unknown": []
        }


    # ========================================================
    # KERNLEISTUNGS-GATE
    # ========================================================

    strong_service_match = (
        bool(title_service_matches)
        or
        electro_cpv_match
    )


    weak_description_match = (
        bool(description_service_matches)
        and
        not strong_service_match
    )


    if not strong_service_match:

        reason = (
            "Keine passende Kernleistung "
            "als Hauptgegenstand erkannt"
        )


        if weak_description_match:

            reason += (
                " – Elektro wird nur "
                "als Nebenleistung erwähnt"
            )


        if foreign_title_matches:

            reason += (
                " – fachfremdes Gewerk: "
                + ", ".join(
                    foreign_title_matches[:3]
                )
            )


        return {
            "eligible": False,
            "score": 0,
            "confidence": 100,
            "ko": True,
            "reasons": [
                "✗ " + reason
            ],
            "unknown": []
        }


    # ========================================================
    # MATCH-BERECHNUNG
    # ========================================================

    score = 0
    confidence = 0

    reasons = []
    unknown = []


    # ========================================================
    # SERVICE / HAUPTLEISTUNG – 50 %
    # ========================================================

    if (
        title_service_matches
        and
        electro_cpv_match
    ):

        score += 50
        confidence += 50

        reasons.append(
            "✓ Kernleistung durch Titel und CPV bestätigt"
        )


    elif electro_cpv_match:

        score += 48
        confidence += 50

        reasons.append(
            "✓ Passender Elektro-CPV-Code"
        )


    elif title_service_matches:

        score += 45
        confidence += 40

        reasons.append(
            "✓ Kernleistung eindeutig im Titel erkannt"
        )


    # ========================================================
    # REGION – 20 %
    # ========================================================

    regions = (
        profile
        .get("location", {})
        .get("regions", [])
    )


    nationwide = (
        profile
        .get("location", {})
        .get("nationwide", False)
    )


    if nationwide:

        score += 20
        confidence += 20

        reasons.append(
            "✓ Einsatzgebiet passt"
        )


    elif location_text:

        confidence += 20


        if contains_any(
            location_text,
            regions
        ):

            score += 20

            reasons.append(
                "✓ Region passt"
            )


        else:

            reasons.append(
                "✗ Region außerhalb des bevorzugten Einsatzgebiets"
            )


    else:

        unknown.append(
            "Region nicht angegeben"
        )


    # ========================================================
    # AUFTRAGSWERT – 15 %
    # ========================================================

    value_profile = profile.get(
        "contract_value",
        {}
    )


    if contract_value is not None:

        confidence += 15


        ideal_min = value_profile.get(
            "ideal_min_eur"
        )


        ideal_max = value_profile.get(
            "ideal_max_eur"
        )


        absolute_max = value_profile.get(
            "absolute_max_eur"
        )


        if (
            absolute_max is not None
            and
            contract_value > absolute_max
        ):

            reasons.append(
                "✗ Auftragswert über Unternehmensgrenze"
            )


        elif (
            ideal_min is not None
            and
            ideal_max is not None
            and
            ideal_min
            <= contract_value
            <= ideal_max
        ):

            score += 15

            reasons.append(
                "✓ Auftragsgröße liegt im Idealbereich"
            )


        else:

            score += 7

            reasons.append(
                "◐ Auftragsgröße möglich, aber nicht ideal"
            )


    else:

        unknown.append(
            "Auftragswert nicht angegeben"
        )


    # ========================================================
    # PROJEKTTYP – 10 %
    # ========================================================

    preferred_projects = profile.get(
        "preferred_projects",
        []
    )


    confidence += 10


    combined_project_text = (
        title_text
        + " "
        + description_text
    )


    if contains_any(
        combined_project_text,
        preferred_projects
    ):

        score += 10

        reasons.append(
            "✓ Bevorzugter Projekttyp"
        )


    else:

        reasons.append(
            "◐ Projekttyp neutral"
        )


    # ========================================================
    # PFLICHTNACHWEISE – 5 %
    # ========================================================

    unknown.append(
        "Pflichtnachweise noch nicht vollständig geprüft"
    )


    final_score = min(
        round(score),
        100
    )


    final_confidence = min(
        round(confidence),
        100
    )


    return {
        "eligible": True,
        "score": final_score,
        "confidence": final_confidence,
        "ko": False,
        "reasons": reasons,
        "unknown": unknown
    }


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(
    chat_id,
    message
):

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


        print(
            "Telegram Fehler:",
            result
        )


    except Exception as error:

        print(
            "Telegram Fehler:",
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


        if isinstance(
            saved,
            list
        ):

            posted_ids = set(
                saved
            )


        else:

            posted_ids = set()


except (
    FileNotFoundError,
    json.JSONDecodeError
):

    posted_ids = set()


new_posted_ids = set()


# ============================================================
# DATUM
# ============================================================

berlin_now = datetime.now(
    ZoneInfo("Europe/Berlin")
)


today_ted = berlin_now.strftime(
    "%Y%m%d"
)


yesterday = (
    berlin_now
    - timedelta(days=1)
)


oe_day = yesterday.strftime(
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
    source,
    location_text="",
    contract_value=None,
    description=""
):

    title = clean_text(
        title
    )


    buyer = clean_text(
        buyer
    )


    number = clean_text(
        number
    )


    if not number:
        return


    category = classify_cpv(
        cpv_codes
    )


    if category is None:
        return


    fingerprint = (
        "FP:"
        +
        create_fingerprint(
            title,
            buyer
        )
    )


    source_key = (
        source
        + ":"
        + number
    )


    if (
        fingerprint in posted_ids
        or
        fingerprint in new_posted_ids
        or
        source_key in posted_ids
        or
        source_key in new_posted_ids
    ):

        return


    # ========================================================
    # MATCHING V3
    # ========================================================

    match = calculate_match(

        title=title,

        buyer=buyer,

        location_text=
            location_text,

        contract_value=
            contract_value,

        cpv_codes=
            cpv_codes,

        description=
            description
    )


    if not match[
        "eligible"
    ]:

        print(
            "⛔ Fachlich aussortiert:",
            title
        )

        return


    score = match[
        "score"
    ]


    confidence = match[
        "confidence"
    ]


    if (
        score
        <
        MINIMUM_MATCH_SCORE
    ):

        print(
            f"⏭ Match zu niedrig: "
            f"{score}% | "
            f"{title}"
        )

        return


    # ========================================================
    # KANAL
    # ========================================================

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


    # ========================================================
    # EMPFEHLUNG
    # ========================================================

    if (
        score >= 85
        and
        confidence >= 70
    ):

        recommendation = (
            "🟢 BEWERBUNG SEHR INTERESSANT"
        )


    elif score >= 75:

        recommendation = (
            "🟢 BEWERBUNG PRÜFEN"
        )


    else:

        recommendation = (
            "🟡 WEITERE PRÜFUNG EMPFOHLEN"
        )


    reasons_text = "\n".join(
        match[
            "reasons"
        ][:6]
    )


    unknown_text = ""


    if match[
        "unknown"
    ]:

        unknown_text = (
            "\n\n⚠ Noch zu prüfen:\n"
            +
            "\n".join(
                "• " + item
                for item
                in match[
                    "unknown"
                ][:4]
            )
        )


    value_text = (
        "Nicht angegeben"
    )


    if contract_value is not None:

        value_text = (
            f"{contract_value:,.0f} €"
            .replace(
                ",",
                "."
            )
        )


    message = (
        f"🎯 {score}% MATCH\n"
        f"📊 {confidence}% DATENSICHERHEIT\n\n"

        f"{recommendation}\n\n"

        f"{category_name}\n\n"

        f"📌 {title[:800]}\n\n"

        f"🏢 Auftraggeber:\n"
        f"{buyer[:350]}\n\n"

        f"📍 Ort:\n"
        f"{location_text or 'Nicht angegeben'}\n\n"

        f"💰 Auftragswert:\n"
        f"{value_text}\n\n"

        f"📅 Veröffentlicht: "
        f"{publication_date}\n\n"

        "Warum passend?\n"
        f"{reasons_text}"

        f"{unknown_text}\n\n"

        f"📡 Quelle: "
        f"{source}\n\n"

        "🔗 Ausschreibung:\n"
        f"{link}"
    )


    success = send_telegram(
        chat_id,
        message
    )


    if success:

        new_posted_ids.add(
            fingerprint
        )

        new_posted_ids.add(
            source_key
        )


        print(
            f"✅ {score}% Match "
            f"({confidence}% Confidence) "
            f"gepostet: {number}"
        )


# ============================================================
# TED
# ============================================================

def fetch_ted():

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

            "place-of-performance-city-proc",
            "place-of-performance-city-lot",

            "place-of-performance-subdiv-proc",
            "place-of-performance-subdiv-lot",

            "estimated-value-proc",
            "estimated-value-lot"
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


    notices = (
        response
        .json()
        .get(
            "notices",
            []
        )
    )


    for notice in notices:

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


        location_text = (

            clean_text(
                notice.get(
                    "place-of-performance-city-proc"
                )
            )

            + " "

            + clean_text(
                notice.get(
                    "place-of-performance-city-lot"
                )
            )

            + " "

            + clean_text(
                notice.get(
                    "place-of-performance-subdiv-proc"
                )
            )

            + " "

            + clean_text(
                notice.get(
                    "place-of-performance-subdiv-lot"
                )
            )

        ).strip()


        contract_value = (
            extract_number(
                notice.get(
                    "estimated-value-proc"
                )
            )
        )


        if (
            contract_value
            is None
        ):

            contract_value = (
                extract_number(
                    notice.get(
                        "estimated-value-lot"
                    )
                )
            )


        number = clean_text(
            notice.get(
                "publication-number"
            )
        )


        process_notice(

            title=
                notice.get(
                    "notice-title"
                ),

            buyer=
                notice.get(
                    "buyer-name"
                ),

            number=
                number,

            publication_date=
                notice.get(
                    "publication-date"
                ),

            cpv_codes=
                cpv_codes,

            location_text=
                location_text,

            contract_value=
                contract_value,

            description=
                "",

            link=(
                "https://ted.europa.eu/"
                "de/notice/-/detail/"
                + number
            ),

            source=
                "TED"
        )


# ============================================================
# ÖFFENTLICHEVERGABE.DE
# ============================================================

def get_oe_buyer(
    release
):

    buyer = release.get(
        "buyer",
        {}
    )


    if isinstance(
        buyer,
        dict
    ):

        name = clean_text(
            buyer.get(
                "name"
            )
        )


        if name:
            return name


    for party in release.get(
        "parties",
        []
    ):

        if (
            "buyer"
            in party.get(
                "roles",
                []
            )
        ):

            name = clean_text(
                party.get(
                    "name"
                )
            )


            if name:
                return name


    return ""


def get_oe_cpv_codes(
    tender
):

    codes = set()


    for item in tender.get(
        "items",
        []
    ):

        codes.update(
            extract_cpv_codes(
                item.get(
                    "classification"
                )
            )
        )


        codes.update(
            extract_cpv_codes(
                item.get(
                    "additionalClassifications"
                )
            )
        )


    return codes


def get_oe_location(
    tender
):

    parts = []


    for item in tender.get(
        "items",
        []
    ):

        delivery = item.get(
            "deliveryAddress",
            {}
        )


        if isinstance(
            delivery,
            dict
        ):

            for key in [
                "locality",
                "region",
                "postalCode",
                "countryName"
            ]:

                value = clean_text(
                    delivery.get(
                        key
                    )
                )


                if value:

                    parts.append(
                        value
                    )


    return " ".join(
        dict.fromkeys(
            parts
        )
    )


def fetch_oeffentliche_vergabe():

    response = requests.get(

        OE_EXPORT_URL,

        params={
            "pubDay": oe_day,
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


    for filename in archive.namelist():

        if not filename.lower().endswith(
            ".json"
        ):

            continue


        try:

            package = json.loads(
                archive.read(
                    filename
                ).decode(
                    "utf-8"
                )
            )


        except Exception:

            continue


        for release in package.get(
            "releases",
            []
        ):

            tender = release.get(
                "tender",
                {}
            )


            if not isinstance(
                tender,
                dict
            ):

                continue


            cpv_codes = (
                get_oe_cpv_codes(
                    tender
                )
            )


            contract_value = (
                extract_number(
                    tender.get(
                        "value"
                    )
                )
            )


            location_text = (
                get_oe_location(
                    tender
                )
            )


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


            filename_only = (
                filename
                .split("/")[-1]
            )


            uuid_match = re.search(

                r"([0-9a-fA-F]{8}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{12})",

                filename_only
            )


            if uuid_match:

                notice_id = (
                    uuid_match
                    .group(1)
                )


            else:

                notice_id = (
                    filename_only
                    .replace(
                        ".json",
                        ""
                    )
                )


            process_notice(

                title=
                    tender.get(
                        "title"
                    ),

                buyer=
                    get_oe_buyer(
                        release
                    ),

                number=
                    number,

                publication_date=
                    release.get(
                        "date"
                    ),

                cpv_codes=
                    cpv_codes,

                location_text=
                    location_text,

                contract_value=
                    contract_value,

                description=
                    tender.get(
                        "description",
                        ""
                    ),

                link=(
                    "https://"
                    "oeffentlichevergabe.de/"
                    "ui/de/search/details"
                    "?noticeId="
                    + notice_id
                ),

                source=(
                    "ÖffentlicheVergabe.de"
                )
            )


# ============================================================
# BEIDE QUELLEN AUSFÜHREN
# ============================================================

try:

    fetch_ted()


except Exception as error:

    print(
        "❌ TED Fehler:",
        error
    )


try:

    fetch_oeffentliche_vergabe()


except Exception as error:

    print(
        "❌ ÖffentlicheVergabe Fehler:",
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

        sorted(
            posted_ids
        ),

        file,

        ensure_ascii=False,

        indent=2
    )


print(
    "✅ Matching V3 abgeschlossen."
)

print(
    "Neue Matches:",
    len(
        new_posted_ids
    )
)
