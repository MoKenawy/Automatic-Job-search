"""Normalisation and deduplication (design §7.3)."""

from app.normalise.country import parse_country
from app.normalise.employer import normalise_employer
from app.normalise.fingerprint import (
    REMOTE_TOKEN,
    UNKNOWN_TOKEN,
    FingerprintParts,
    build_fingerprint,
)
from app.normalise.title import normalise_title

__all__ = [
    "REMOTE_TOKEN",
    "UNKNOWN_TOKEN",
    "FingerprintParts",
    "build_fingerprint",
    "normalise_employer",
    "normalise_title",
    "parse_country",
]
