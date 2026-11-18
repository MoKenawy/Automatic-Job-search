"""Map our country vocabulary onto JobSpy 1.4's `Country` values.

Two vocabularies, kept apart on purpose:

* **Ours** — `app.normalise.country`, a frozen table of ISO2 codes and English
  names. It feeds the dedup fingerprint, so it must not move when JobSpy does,
  and it imports nothing from JobSpy.
* **JobSpy's** — the `Country` enum, whose values `scrape_jobs(country_indeed=...)`
  accepts. Since 1.4.0 those values are bare lower-case names ("egypt", "uk",
  "türkiye"), invalid ones raise `ValueError`, and ten countries were dropped.

This module is the one seam between them, used where a profile's country is
handed to JobSpy (`collect/sites.py`). It is a literal table, not a lookup into
JobSpy at import, so a JobSpy upgrade cannot change it silently; the contract
tests in `tests/test_jobspy_country.py` fail instead and say what moved.
"""

from app.normalise.country import NAME_TO_ISO2

# The JobSpy version this table was written against (see PINNED_JOBSPY in
# tests/test_jobspy_contract.py).
JOBSPY_VERSION = "1.4.1"

# {our ISO2: JobSpy 1.4 `Country` value}. Generated from JobSpy 1.4.1's own
# Indeed code table (`jobspy.indeed.constant.country_codes`), so each key is the
# code JobSpy itself uses for that country. Note the two that are not plain
# names: "gb" -> "uk" and "tr" -> "türkiye".
JOBSPY_COUNTRY: dict[str, str] = {
    "ae": "united arab emirates",
    "ar": "argentina",
    "at": "austria",
    "au": "australia",
    "be": "belgium",
    "bh": "bahrain",
    "br": "brazil",
    "ca": "canada",
    "ch": "switzerland",
    "cl": "chile",
    "cn": "china",
    "co": "colombia",
    "cr": "costa rica",
    "cz": "czech republic",
    "de": "germany",
    "dk": "denmark",
    "ec": "ecuador",
    "eg": "egypt",
    "es": "spain",
    "fi": "finland",
    "fr": "france",
    "gb": "uk",
    "gr": "greece",
    "hk": "hong kong",
    "hu": "hungary",
    "id": "indonesia",
    "ie": "ireland",
    "il": "israel",
    "in": "india",
    "it": "italy",
    "jp": "japan",
    "kr": "south korea",
    "kw": "kuwait",
    "lu": "luxembourg",
    "ma": "morocco",
    "mx": "mexico",
    "my": "malaysia",
    "ng": "nigeria",
    "nl": "netherlands",
    "no": "norway",
    "nz": "new zealand",
    "om": "oman",
    "pa": "panama",
    "pe": "peru",
    "ph": "philippines",
    "pk": "pakistan",
    "pl": "poland",
    "pt": "portugal",
    "qa": "qatar",
    "ro": "romania",
    "sa": "saudi arabia",
    "se": "sweden",
    "sg": "singapore",
    "th": "thailand",
    "tr": "türkiye",
    "tw": "taiwan",
    "ua": "ukraine",
    "us": "usa",
    "uy": "uruguay",
    "ve": "venezuela",
    "vn": "vietnam",
    "za": "south africa",
}

# In our table, but dropped from JobSpy's `Country` enum in 1.4.0: no Indeed or
# Glassdoor site to search. They stay in our vocabulary because postings from
# them must still fingerprint (a board can still *return* a posting located there).
UNSUPPORTED_BY_JOBSPY: frozenset[str] = frozenset(
    {"bd", "bg", "cy", "ee", "hr", "lt", "lv", "mt", "sk", "sl"}
)


class UnsupportedCountry(ValueError):
    """A country JobSpy cannot search (unknown to us, or dropped by JobSpy)."""


def to_iso2(country: str | None) -> str | None:
    """Our ISO2 code for a country name or code as a profile records it."""
    if not country:
        return None
    return NAME_TO_ISO2.get(" ".join(country.split()).lower())


def to_jobspy(country: str | None) -> str:
    """The `country_indeed` value JobSpy 1.4 expects for one of our countries.

    Accepts any name or code in our table ("egypt", "EG", "United Kingdom",
    "czechia"). Raises `UnsupportedCountry` rather than guessing: passing
    nothing would make JobSpy default to the USA, a wrong search that looks
    like a working one.
    """
    iso2 = to_iso2(country)
    if iso2 is None:
        raise UnsupportedCountry(f"unknown country {country!r}")
    if iso2 in UNSUPPORTED_BY_JOBSPY:
        raise UnsupportedCountry(
            f"{country!r} ({iso2.upper()}) has no Indeed/Glassdoor site in JobSpy {JOBSPY_VERSION}"
        )
    return JOBSPY_COUNTRY[iso2]


def from_jobspy(value: str) -> str | None:
    """Our ISO2 code for a JobSpy `Country` value, or None if it has none."""
    return next((iso2 for iso2, v in JOBSPY_COUNTRY.items() if v == value), None)
