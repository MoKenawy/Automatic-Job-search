"""Resolve a board's flattened location string to an ISO 3166-1 alpha-2 code.

This exists because `scrape_jobs` flattens JobSpy's internal Location object to a
display string, and boards disagree on how to render it (design §7.3.1):

    Indeed     'القاهرة, C, EG'          city localised to Arabic, ISO2 country
    Indeed     'القاهرة, C, Egypt'       the same, as JobSpy >= 1.4 renders it
    LinkedIn   'Cairo, Egypt'            English city, country name
    LinkedIn   'Cairo, Cairo, Egypt'     governorate repeated

Only the final segment is needed, and in every observed form it is Latin script —
either an ISO2 code or an English country name. City localisation therefore does
not obstruct country resolution, which is precisely why the fingerprint resolves
to country rather than city.
"""

import re
import unicodedata

# {ISO2: English names} as JobSpy 1.1.82's Country enum rendered them, frozen.
#
# This used to be derived from `jobspy.model.Country` at import. JobSpy 1.4.0
# reshaped that enum to bare names (no codes) and dropped ten countries, which
# left the derived map empty — every posting's country would have resolved to
# None and every fingerprint would have changed. The country is part of the
# dedup fingerprint (design §7.3), so the vocabulary must not move when the
# library does: it is owned here now.
#
# Kept verbatim, quirks included: Slovenia is "sl" (JobSpy's subdomain, not the
# ISO "si") because fingerprints already stored use it.
_ISO2_NAMES: dict[str, tuple[str, ...]] = {
    "ae": ("united arab emirates",),
    "ar": ("argentina",),
    "at": ("austria",),
    "au": ("australia",),
    "bd": ("bangladesh",),
    "be": ("belgium",),
    "bg": ("bulgaria",),
    "bh": ("bahrain",),
    "br": ("brazil",),
    "ca": ("canada",),
    "ch": ("switzerland",),
    "cl": ("chile",),
    "cn": ("china",),
    "co": ("colombia",),
    "cr": ("costa rica",),
    "cy": ("cyprus",),
    "cz": (
        "czech republic",
        "czechia",
    ),
    "de": ("germany",),
    "dk": ("denmark",),
    "ec": ("ecuador",),
    "ee": ("estonia",),
    "eg": ("egypt",),
    "es": ("spain",),
    "fi": ("finland",),
    "fr": ("france",),
    "gb": (
        "uk",
        "united kingdom",
    ),
    "gr": ("greece",),
    "hk": ("hong kong",),
    "hr": ("croatia",),
    "hu": ("hungary",),
    "id": ("indonesia",),
    "ie": ("ireland",),
    "il": ("israel",),
    "in": ("india",),
    "it": ("italy",),
    "jp": ("japan",),
    "kr": ("south korea",),
    "kw": ("kuwait",),
    "lt": ("lithuania",),
    "lu": ("luxembourg",),
    "lv": ("latvia",),
    "ma": ("morocco",),
    "mt": ("malta",),
    "mx": ("mexico",),
    "my": ("malaysia",),
    "ng": ("nigeria",),
    "nl": ("netherlands",),
    "no": ("norway",),
    "nz": ("new zealand",),
    "om": ("oman",),
    "pa": ("panama",),
    "pe": ("peru",),
    "ph": ("philippines",),
    "pk": ("pakistan",),
    "pl": ("poland",),
    "pt": ("portugal",),
    "qa": ("qatar",),
    "ro": ("romania",),
    "sa": ("saudi arabia",),
    "se": ("sweden",),
    "sg": ("singapore",),
    "sk": ("slovakia",),
    "sl": ("slovenia",),
    "th": ("thailand",),
    "tr": (
        "turkey",
        "türkiye",
    ),
    "tw": ("taiwan",),
    "ua": ("ukraine",),
    "us": (
        "united states",
        "usa",
    ),
    "uy": ("uruguay",),
    "ve": ("venezuela",),
    "vn": ("vietnam",),
    "za": ("south africa",),
}


def _build_name_map() -> dict[str, str]:
    """{country name or ISO2: ISO2} from the frozen table."""
    mapping: dict[str, str] = {}
    for iso2, names in _ISO2_NAMES.items():
        mapping[iso2] = iso2
        for name in names:
            mapping[name] = iso2
    return mapping


NAME_TO_ISO2 = _build_name_map()

# Arabic country names, for the case where a board localises the country segment
# too. Deliberately a small closed set: unlike city names (§7.3.1) the country
# vocabulary is bounded, and an unmapped value returns None rather than failing
# silently to a wrong code.
ARABIC_COUNTRY_ALIASES = {
    "مصر": "eg",
    "السعودية": "sa",
    "المملكة العربية السعودية": "sa",
    "الإمارات": "ae",
    "الامارات": "ae",
    "الإمارات العربية المتحدة": "ae",
    "قطر": "qa",
    "الكويت": "kw",
    "البحرين": "bh",
    "عمان": "om",
    "الأردن": "jo",
    "لبنان": "lb",
    "المغرب": "ma",
    "تونس": "tn",
    "الجزائر": "dz",
}

_PUNCT = re.compile(r"[^\w\s؀-ۿ]", flags=re.UNICODE)


def _clean(segment: str) -> str:
    """Lowercase, strip accents from Latin text, drop punctuation."""
    segment = unicodedata.normalize("NFKD", segment)
    segment = "".join(c for c in segment if not unicodedata.combining(c))
    segment = _PUNCT.sub(" ", segment)
    return " ".join(segment.split()).lower()


def parse_country(location_raw: str | None) -> str | None:
    """Return an uppercase ISO2 code, or None if it cannot be determined.

    Returning None is deliberate. A wrong code merges unrelated postings across
    countries, which conceals a posting — the intolerable failure in §7.3. An
    unresolved country is instead counted per run so the gap stays visible.
    """
    if not location_raw:
        return None

    segments = [s for s in str(location_raw).split(",") if s.strip()]
    if not segments:
        return None

    # Work backwards: the country is the last meaningful segment, but a trailing
    # postcode or stray token should not defeat the lookup.
    for segment in reversed(segments):
        cleaned = _clean(segment)
        if not cleaned:
            continue
        if cleaned in NAME_TO_ISO2:
            return NAME_TO_ISO2[cleaned].upper()
        raw = segment.strip()
        if raw in ARABIC_COUNTRY_ALIASES:
            return ARABIC_COUNTRY_ALIASES[raw].upper()
        if cleaned in ARABIC_COUNTRY_ALIASES:
            return ARABIC_COUNTRY_ALIASES[cleaned].upper()

    return None
