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
# GRUNDEINSTELLUNGEN
# ============================================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

BAU_CHAT = os.getenv("TELEGRAM_CHAT_ID")
IT_CHAT = os.getenv("TELEGRAM_IT_CHAT_ID")

POSTED_FILE = "posted_ids.json"

BAU_PROFILE_FILE = "company_profile.json"
IT_PROFILE_FILE = "company_profile_it.json"

TED_URL = "https://api.ted.europa.eu/v3/notices/search"

OE_EXPORT_URL = (
    "https://oeffentlichevergabe.de/api/notice-exports"
)


# ============================================================
# PROFILE LADEN
# ============================================================

with open(
    BAU_PROFILE_FILE,
    "r",
    encoding="utf-8"
) as file:
    BAU_PROFILE = json.load(file)


with open(
    IT_PROFILE_FILE,
    "r",
    encoding="utf-8"
) as file:
    IT_PROFILE = json.load(file)


# ============================================================
# CPV-KATEGORIEN
# ============================================================

BAU_PREFIXES = ("45",)

IT_PREFIXES = (
    "48",
    "72"
)


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
    "45313",
    "453154",
    "453155"
)


# ============================================================
# BAU / ELEKTRO
# ============================================================

BAU_SERVICE_ALIASES = [
    "elektro",
    "elektrik",
    "elektrisch",
    "elektrotechnik",
    "elektroinstallation",
    "elektroinstallationsarbeiten",
    "elektroarbeiten",
    "elektroanlage",
    "elektroanlagen",
    "starkstrom",
    "schwachstrom",
    "niederspannung",
    "niederspannungsanlage",
    "beleuchtung",
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
    "brandmeldetechnik",
    "bma",
    "elektrische installation"
]


BAU_FOREIGN_KEYWORDS = [
    "brückenbau",
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
    "stahlbetonarbeiten",
    "mauerarbeiten",
    "zimmerarbeiten",
    "dachdeckerarbeiten",
    "abbrucharbeiten",
    "bodenbelagarbeiten",
    "fassadensanierung",
    "regenentwässerung",
    "heizung und sanitär",
    "heizungsarbeiten",
    "sanitärarbeiten"
]


# ============================================================
# IT
# ============================================================

IT_SERVICE_ALIASES = [
    "softwareentwicklung",
    "softwarepflege",
    "softwarewartung",
    "anwendungsentwicklung",
    "webentwicklung",
    "webanwendung",
    "webanwendungen",
    "webportal",
    "onlineportal",
    "fachanwendung",
    "appentwicklung",
    "mobile app",
    "digitalisierung",
    "it-dienstleistung",
    "it-dienstleistungen",
    "it-beratung",
    "it consulting",
    "systemintegration",
    "systemmanagement",
    "servermanagement",
    "infrastrukturmanagement",
    "cloud service",
    "cloud services",
    "datenbankentwicklung",
    "api entwicklung",
    "schnittstellenentwicklung",
    "it-infrastruktur",
    "netzwerkmanagement",
    "cybersecurity",
    "it-sicherheit",
    "weiterentwicklung der software",
    "weiterentwicklung der anwendung",
    "pflege und weiterentwicklung",
    "betrieb einer it-anwendung",
    "betrieb einer software"
]


# Begriffe, die allein noch NICHT reichen,
# um einen guten IT-Match zu erzeugen.

IT_GENERIC_TERMS = [
    "software",
    "it",
    "app",
    "cloud",
    "server",
    "netzwerk",
    "lizenz",
    "lizenzen"
]


# Hard-K.O.-Kandidaten

IT_EXCLUDED_MAIN_SERVICES = [
    "lizenzverlängerung",
    "verlängerung von lizenzen",
    "lizenzbeschaffung",
    "beschaffung von lizenzen",
    "softwarelizenzen",
    "software-lizenzen",
    "subscription verlängerung",
    "abonnementverlängerung",
    "hardwarelieferung",
    "hardwarebeschaffung",
    "druckerlieferung",
    "druckerbeschaffung",
    "mobilfunkvertrag",
    "mobilfunkverträge",
    "telefonvertrag",
    "telefonverträge"
]


# Begriffe, die zeigen, dass trotz Lizenz/Hardware
# eine relevante Dienstleistung enthalten ist.

IT_OVERRIDE_SERVICE_TERMS = [
    "entwicklung",
    "softwareentwicklung",
    "anwendungsentwicklung",
    "weiterentwicklung",
    "pflege",
    "wartung",
    "betrieb",
    "migration",
    "integration",
    "implementierung",
    "customizing",
    "beratung",
    "support",
    "systemmanagement",
    "projektleistung",
    "dienstleistung"
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


def contains_any(
    text,
    keywords
):

    normalized_text = normalize(text)

    for keyword in keywords:

        normalized_keyword = normalize(
            keyword
        )

        if (
            normalized_keyword
            and
            normalized_keyword in normalized_text
        ):
            return True

    return False


def matching_keywords(
    text,
    keywords
):

    normalized_text = normalize(text)

    matches = []

    for keyword in keywords:

        normalized_keyword = normalize(
            keyword
        )

        if (
            normalized_keyword
            and
            normalized_keyword in normalized_text
        ):

            matches.append(
                keyword
            )

    return matches


def extract_number(value):

    if value is None:
        return None

    if isinstance(value, list):

        for item in value:

            result = extract_number(
                item
            )

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

            result = extract_number(
                item
            )

            if result is not None:
                return result

        return None

    try:

        return float(value)

    except Exception:

        match = re.search(
            r"\d+(?:[.,]\d+)?",
            str(value)
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


# ============================================================
# CPV
# ============================================================

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
                extract_cpv_codes(
                    item
                )
            )

    elif isinstance(value, list):

        for item in value:

            codes.update(
                extract_cpv_codes(
                    item
                )
            )

    else:

        matches = re.findall(
            r"(?<!\d)(\d{8})(?!\d)",
            str(value)
        )

        codes.update(
            matches
        )

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

    if (
        has_bau
        and
        not has_it
    ):
        return "bau"

    if (
        has_it
        and
        not has_bau
    ):
        return "it"

    return None


def has_relevant_electro_cpv(
    codes
):

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


def has_excluded_electro_cpv(
    codes
):

    return any(
        code.startswith(
            ELECTRO_CPV_EXCLUDED_PREFIXES
        )
        for code in codes
    )


# ============================================================
# DUPLIKATE
# ============================================================

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


# ============================================================
# BAU-MATCHING
# ============================================================

def calculate_bau_match(
    title,
    location_text,
    contract_value,
    cpv_codes,
    description=""
):

    profile = BAU_PROFILE

    title_text = normalize(
        title
    )

    description_text = normalize(
        description
    )


    services = list(
        profile.get(
            "services",
            []
        )
    )

    services.extend(
        BAU_SERVICE_ALIASES
    )


    title_matches = matching_keywords(
        title_text,
        services
    )


    description_matches = matching_keywords(
        description_text,
        services
    )


    electro_cpv = (
        has_relevant_electro_cpv(
            cpv_codes
        )
    )


    excluded_cpv = (
        has_excluded_electro_cpv(
            cpv_codes
        )
    )


    foreign_title = matching_keywords(
        title_text,
        BAU_FOREIGN_KEYWORDS
    )


    if excluded_cpv:

        return {
            "eligible": False,
            "score": 0,
            "confidence": 100,
            "reasons": [
                "✗ Elektrobereich passt nicht zum Unternehmensprofil"
            ],
            "unknown": []
        }


    strong_service_match = (
        bool(title_matches)
        or
        electro_cpv
    )


    if not strong_service_match:

        reason = (
            "Keine Elektro-Kernleistung "
            "als Hauptgegenstand erkannt"
        )


        if description_matches:

            reason += (
                " – Elektro nur als Nebenleistung erwähnt"
            )


        if foreign_title:

            reason += (
                " – fachfremdes Gewerk: "
                + ", ".join(
                    foreign_title[:3]
                )
            )


        return {
            "eligible": False,
            "score": 0,
            "confidence": 100,
            "reasons": [
                "✗ " + reason
            ],
            "unknown": []
        }


    score = 70
    confidence = 45

    reasons = []
    unknown = []


    if (
        title_matches
        and
        electro_cpv
    ):

        score = 80
        confidence = 55

        reasons.append(
            "✓ Kernleistung durch Titel und CPV bestätigt"
        )


    elif title_matches:

        score = 75

        reasons.append(
            "✓ Elektro-Kernleistung im Titel erkannt"
        )


    elif electro_cpv:

        score = 72
        confidence = 50

        reasons.append(
            "✓ Passender Elektro-CPV-Code"
        )


    preferred_projects = profile.get(
        "preferred_projects",
        []
    )


    combined_text = (
        title_text
        + " "
        + description_text
    )


    if contains_any(
        combined_text,
        preferred_projects
    ):

        score += 8

        reasons.append(
            "✓ Bevorzugter Projekttyp"
        )


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

        score += 7
        confidence += 15

        reasons.append(
            "✓ Einsatzgebiet passt"
        )


    elif location_text:

        confidence += 15


        if contains_any(
            location_text,
            regions
        ):

            score += 10

            reasons.append(
                "✓ Region passt"
            )


        else:

            score -= 20

            reasons.append(
                "✗ Region außerhalb des Einsatzgebiets"
            )


    else:

        unknown.append(
            "Region nicht angegeben"
        )


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

            score -= 20

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

            score += 10

            reasons.append(
                "✓ Auftragswert im Idealbereich"
            )


        else:

            score += 3

            reasons.append(
                "◐ Auftragswert grundsätzlich möglich"
            )


    else:

        unknown.append(
            "Auftragswert nicht angegeben"
        )


    unknown.append(
        "Pflichtnachweise noch nicht vollständig geprüft"
    )


    return {
        "eligible": True,
        "score": max(
            0,
            min(
                round(score),
                100
            )
        ),
        "confidence": min(
            confidence,
            95
        ),
        "reasons": reasons,
        "unknown": unknown
    }


# ============================================================
# IT-MATCHING V5
# ============================================================

def calculate_it_match(
    title,
    location_text,
    contract_value,
    cpv_codes,
    description=""
):

    profile = IT_PROFILE

    title_text = normalize(
        title
    )

    description_text = normalize(
        description
    )

    combined_text = (
        title_text
        + " "
        + description_text
    )


    # ========================================================
    # 1. AUSSCHLUSSKRITERIEN PRÜFEN
    # ========================================================

    excluded_profile_terms = (
        profile.get(
            "excluded_services",
            []
        )
    )

    all_excluded_terms = (
        excluded_profile_terms
        +
        IT_EXCLUDED_MAIN_SERVICES
    )


    exclusion_matches = matching_keywords(
        title_text,
        all_excluded_terms
    )


    override_matches = matching_keywords(
        combined_text,
        IT_OVERRIDE_SERVICE_TERMS
    )


    # Wenn der Titel klar reine Lizenz-/Hardwarebeschaffung
    # beschreibt und keine relevante Dienstleistung erkennbar ist:
    # HARD K.O.

    if (
        exclusion_matches
        and
        not override_matches
    ):

        return {
            "eligible": False,
            "score": 0,
            "confidence": 100,
            "reasons": [
                "✗ Hauptgegenstand ist eine ausgeschlossene IT-Leistung: "
                + ", ".join(
                    exclusion_matches[:3]
                )
            ],
            "unknown": []
        }


    # ========================================================
    # 2. RELEVANTE IT-LEISTUNG ERKENNEN
    # ========================================================

    services = list(
        profile.get(
            "services",
            []
        )
    )

    services.extend(
        IT_SERVICE_ALIASES
    )


    title_matches = matching_keywords(
        title_text,
        services
    )


    description_matches = matching_keywords(
        description_text,
        services
    )


    # Allgemeines Wort "Software" oder "IT" reicht NICHT.
    # Wir wollen möglichst echte Dienstleistungen erkennen.

    strong_title_matches = [
        item
        for item in title_matches
        if normalize(item)
        not in [
            normalize(x)
            for x in IT_GENERIC_TERMS
        ]
    ]


    if (
        not strong_title_matches
        and
        not description_matches
        and
        not override_matches
    ):

        return {
            "eligible": False,
            "score": 0,
            "confidence": 100,
            "reasons": [
                "✗ Keine relevante IT-Dienstleistung erkannt"
            ],
            "unknown": []
        }


    # ========================================================
    # 3. SCORE
    # ========================================================

    score = 68
    confidence = 45

    reasons = []
    unknown = []


    if strong_title_matches:

        score = 80
        confidence = 55

        reasons.append(
            "✓ Relevante IT-Kernleistung im Titel erkannt"
        )


    elif override_matches:

        score = 76
        confidence = 50

        reasons.append(
            "✓ Relevante IT-Dienstleistung erkannt"
        )


    elif description_matches:

        score = 70

        reasons.append(
            "✓ IT-Dienstleistung in der Beschreibung erkannt"
        )


    # ========================================================
    # Projekttyp
    # ========================================================

    preferred_projects = profile.get(
        "preferred_projects",
        []
    )


    if contains_any(
        combined_text,
        preferred_projects
    ):

        score += 8

        reasons.append(
            "✓ Bevorzugter IT-Projekttyp"
        )


    # ========================================================
    # Region
    # ========================================================

    nationwide = (
        profile
        .get("location", {})
        .get(
            "nationwide",
            False
        )
    )


    regions = (
        profile
        .get("location", {})
        .get(
            "regions",
            []
        )
    )


    if nationwide:

        score += 7
        confidence += 15

        reasons.append(
            "✓ Deutschlandweites Einsatzgebiet"
        )


    elif location_text:

        confidence += 15


        if contains_any(
            location_text,
            regions
        ):

            score += 10

            reasons.append(
                "✓ Region passt"
            )


        else:

            score -= 15

            reasons.append(
                "✗ Region außerhalb des Einsatzgebiets"
            )


    else:

        unknown.append(
            "Region nicht angegeben"
        )


    # ========================================================
    # Auftragswert
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

            score -= 20

            reasons.append(
                "✗ Auftrag größer als Unternehmensgrenze"
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

            score += 10

            reasons.append(
                "✓ Auftragsgröße im Idealbereich"
            )


        else:

            score += 3

            reasons.append(
                "◐ Auftragswert grundsätzlich möglich"
            )


    else:

        unknown.append(
            "Auftragswert nicht angegeben"
        )


    unknown.append(
        "Pflichtnachweise noch nicht vollständig geprüft"
    )


    return {
        "eligible": True,
        "score": max(
            0,
            min(
                round(score),
                100
            )
        ),
        "confidence": min(
            confidence,
            95
        ),
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
# GEDÄCHTNIS
# ============================================================

try:

    with open(
        POSTED_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        saved = json.load(
            file
        )


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


oe_day = (
    berlin_now
    - timedelta(days=1)
).strftime(
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
    # PROFIL AUSWÄHLEN
    # ========================================================

    if category == "bau":

        profile = BAU_PROFILE
        chat_id = BAU_CHAT

        category_name = (
            "🏗 Bau & Infrastruktur"
        )

        match = calculate_bau_match(
            title=title,
            location_text=location_text,
            contract_value=contract_value,
            cpv_codes=cpv_codes,
            description=description
        )


    else:

        profile = IT_PROFILE
        chat_id = IT_CHAT

        category_name = (
            "💻 IT, Software & Digitalisierung"
        )

        match = calculate_it_match(
            title=title,
            location_text=location_text,
            contract_value=contract_value,
            cpv_codes=cpv_codes,
            description=description
        )


    if not match[
        "eligible"
    ]:

        print(
            f"⛔ {category.upper()} "
            f"fachlich aussortiert: "
            f"{title}"
        )

        return


    score = match[
        "score"
    ]

    confidence = match[
        "confidence"
    ]


    minimum_score = (
        profile
        .get("matching", {})
        .get(
            "minimum_match_score",
            70
        )
    )


    if score < minimum_score:

        print(
            f"⏭ {category.upper()} "
            f"Match zu niedrig: "
            f"{score}% | {title}"
        )

        return


    if (
        score >= 90
        and
        confidence >= 70
    ):

        recommendation = (
            "🟢 SEHR STARKER MATCH"
        )


    elif score >= 80:

        recommendation = (
            "🟢 GUTER MATCH"
        )


    else:

        recommendation = (
            "🟡 INTERESSANT – DETAILS PRÜFEN"
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


    company_name = profile.get(
        "company_name",
        "Testunternehmen"
    )


    message = (
        f"🎯 {score}% MATCH\n"
        f"📊 {confidence}% DATENSICHERHEIT\n\n"

        f"{recommendation}\n\n"

        f"{category_name}\n\n"

        f"🏢 Match-Profil:\n"
        f"{company_name}\n\n"

        f"📌 {title[:800]}\n\n"

        f"🏛 Auftraggeber:\n"
        f"{buyer[:350]}\n\n"

        f"📍 Ort:\n"
        f"{location_text or 'Nicht angegeben'}\n\n"

        f"💰 Auftragswert:\n"
        f"{value_text}\n\n"

        f"📅 Veröffentlicht:\n"
        f"{publication_date}\n\n"

        f"Warum passend?\n"
        f"{reasons_text}"

        f"{unknown_text}\n\n"

        f"📡 Quelle: "
        f"{source}\n\n"

        f"🔗 Ausschreibung:\n"
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
            f"✅ {category.upper()} "
            f"{score}% Match "
            f"({confidence}% Confidence): "
            f"{title}"
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
            +
            clean_text(
                notice.get(
                    "place-of-performance-city-lot"
                )
            )
            + " "
            +
            clean_text(
                notice.get(
                    "place-of-performance-subdiv-proc"
                )
            )
            + " "
            +
            clean_text(
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


        if contract_value is None:

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
            title=notice.get(
                "notice-title"
            ),
            buyer=notice.get(
                "buyer-name"
            ),
            number=number,
            publication_date=notice.get(
                "publication-date"
            ),
            cpv_codes=cpv_codes,
            location_text=location_text,
            contract_value=contract_value,
            description="",
            link=(
                "https://ted.europa.eu/"
                "de/notice/-/detail/"
                + number
            ),
            source="TED"
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
                title=tender.get(
                    "title"
                ),
                buyer=get_oe_buyer(
                    release
                ),
                number=number,
                publication_date=release.get(
                    "date"
                ),
                cpv_codes=cpv_codes,
                location_text=location_text,
                contract_value=contract_value,
                description=tender.get(
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
# QUELLEN AUSFÜHREN
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
    "✅ Matching V5 abgeschlossen."
)


print(
    "Neue Matches:",
    len(
        new_posted_ids
    )
)
