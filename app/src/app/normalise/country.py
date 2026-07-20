"""Resolve a board's flattened location string to an ISO 3166-1 alpha-2 code.

This exists because `scrape_jobs` flattens JobSpy's internal Location object to a
display string, and boards disagree on how to render it (design §7.3.1):

    Indeed     'القاهرة, C, EG'          city localised to Arabic, ISO2 country
    LinkedIn   'Cairo, Egypt'            English city, country name
    LinkedIn   'Cairo, Cairo, Egypt'     governorate repeated

Only the final segment is needed, and in every observed form it is Latin script —
either an ISO2 code or an English country name. City localisation therefore does
not obstruct country resolution, which is precisely why the fingerprint resolves
to country rather than city.
"""

import re
import unicodedata

from jobspy.model import Country

# Country enum entries that are not countries and must not enter the map
_NOT_COUNTRIES = {"WORLDWIDE", "US_CANADA"}


def _build_name_map() -> dict[str, str]:
    """Derive {country name or code: ISO2} from JobSpy's own Country enum.

    Enum values are (comma-separated names, 'subdomain[:iso2]', [glassdoor domain]),
    e.g. EGYPT -> ('egypt', 'eg'), UK -> ('uk,united kingdom', 'uk:gb').
    The ISO2 is the segment after the colon where present, else the subdomain.
    """
    mapping: dict[str, str] = {}
    for country in Country:
        if country.name in _NOT_COUNTRIES:
            continue
        value = country.value
        if not isinstance(value, tuple) or len(value) < 2:
            continue
        names, domain = value[0], value[1]
        iso2 = domain.split(":")[-1].strip().lower()
        if len(iso2) != 2:
            continue
        for name in names.split(","):
            name = name.strip().lower()
            if name:
                mapping[name] = iso2
        mapping[iso2] = iso2
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
