"""Employer name normalisation.

Deliberately conservative, per design §7.3: legal-entity suffixes are removed;
descriptor words such as Technologies, Solutions or Group are retained. Removing
descriptors merges genuinely distinct employers that share a root name. Showing
one posting twice is a nuisance; concealing a posting behind a false merge is a
lost opportunity.
"""

import re
import unicodedata

# Legal-entity suffixes only. Note S.A.E. — the Egyptian joint-stock form —
# which appears in local listings.
LEGAL_SUFFIXES = {
    "inc",
    "incorporated",
    "llc",
    "lc",
    "ltd",
    "limited",
    "llp",
    "lp",
    "plc",
    "corp",
    "corporation",
    "co",
    "company",
    "gmbh",
    "mbh",
    "ag",
    "sa",
    "sae",
    "sas",
    "sarl",
    "spa",
    "srl",
    "bv",
    "nv",
    "ab",
    "as",
    "oy",
    "aps",
    "pty",
    "pte",
    "kk",
    "wll",  # Gulf: with limited liability
    "fzco",
    "fze",
    "fzllc",  # UAE free-zone forms
}

_ARABIC = re.compile(r"[؀-ۿݐ-ݿ]")
_LATIN = re.compile(r"[A-Za-z]")
_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)

# Dotted acronyms, e.g. 'S.A.E.' or 'W.L.L.'. These must be collapsed *before*
# punctuation is stripped, or they fragment into single-letter tokens ('s a e')
# and no longer match the legal-suffix set.
_DOTTED_ACRONYM = re.compile(r"\b(?:[A-Za-z]\.){2,}")


def _strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def _prefer_latin(name: str) -> str:
    """For bilingual names, keep the Latin portion.

    Regional listings commonly carry both scripts, e.g. 'Halan - حالا'. One board
    may render only the Latin form, so keeping both would defeat the match. Where
    a name is Arabic-only, it is left untouched.
    """
    if not (_ARABIC.search(name) and _LATIN.search(name)):
        return name
    # Split on the separators used for bilingual branding, keep Latin-bearing parts
    parts = re.split(r"[-–—|/]", name)
    latin_parts = [p for p in parts if _LATIN.search(p) and not _ARABIC.search(p)]
    if latin_parts:
        return " ".join(latin_parts)
    # Interleaved rather than separated: drop the Arabic characters
    return _ARABIC.sub(" ", name)


def normalise_employer(name: str | None) -> str:
    """Return a comparable employer key. Empty string if the name is unusable."""
    if not name:
        return ""

    name = _prefer_latin(str(name))
    name = _strip_accents(name)
    name = _DOTTED_ACRONYM.sub(lambda m: m.group(0).replace(".", ""), name)
    name = _PUNCT.sub(" ", name)
    tokens = name.lower().split()

    # Strip legal suffixes from the tail only. A suffix word appearing mid-name
    # is part of the name proper (e.g. 'Company of Egypt').
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()

    return " ".join(tokens)
