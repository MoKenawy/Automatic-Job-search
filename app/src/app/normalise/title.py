"""Job title normalisation.

Conservative by intent. Seniority and discipline markers are *retained* — merging
'Senior Data Engineer' with 'Data Engineer' would conceal a posting, the failure
mode §7.3 exists to avoid. Only cosmetic variation is removed: case, accents,
punctuation, gender markers, and trailing requisition identifiers.
"""

import re
import unicodedata

# Gender-inclusivity markers, common in EU listings: (m/f/d), (m/w/d), (f/m/x)
_GENDER_MARKER = re.compile(r"\(\s*[mfwdxhq](\s*/\s*[mfwdxhq])+\s*\)", flags=re.IGNORECASE)

# Trailing requisition or job identifiers: '- 12345', '(REQ-9981)', '#4471'
_REQ_ID = re.compile(
    r"[\s\-–—|(\[]*\b(?:job\s*id|req(?:uisition)?(?:\s*id)?|ref|id)\b[\s:#-]*[\w-]+[)\]]*$",
    flags=re.IGNORECASE,
)
_TRAILING_NUMBER = re.compile(r"[\s\-–—|(\[#]+\d{3,}[)\]]*$")

_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)


def normalise_title(title: str | None) -> str:
    """Return a comparable title key. Empty string if the title is unusable."""
    if not title:
        return ""

    text = str(title)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    text = _GENDER_MARKER.sub(" ", text)
    text = _REQ_ID.sub("", text)
    text = _TRAILING_NUMBER.sub("", text)

    text = _PUNCT.sub(" ", text)
    return " ".join(text.split()).lower()
