"""Deterministic posting fingerprint.

Derived from normalised employer, normalised title and country (design D12,
§7.3.1). City is deliberately excluded: boards localise city names
irreconcilably, so including it guarantees the duplicates this exists to prevent.

Remote roles collapse to a single location token, since boards disagree on the
nominal location of a remote role (design §7.3).
"""

import hashlib
from dataclasses import dataclass

from app.normalise.country import parse_country
from app.normalise.employer import normalise_employer
from app.normalise.title import normalise_title

# Location token used for remote roles, replacing the country component
REMOTE_TOKEN = "REMOTE"
# Location token used when the country could not be resolved. Distinct from
# REMOTE so that unresolved locations are countable per run (design §7.4)
# rather than silently merging into the remote bucket.
UNKNOWN_TOKEN = "UNKNOWN"


@dataclass(frozen=True)
class FingerprintParts:
    """The inputs to a fingerprint, retained for storage and diagnosis."""

    employer: str
    title: str
    location: str
    digest: str

    @property
    def country_resolved(self) -> bool:
        return self.location not in (UNKNOWN_TOKEN, REMOTE_TOKEN)


def build_fingerprint(
    *,
    employer: str | None,
    title: str | None,
    location_raw: str | None,
    is_remote: bool = False,
) -> FingerprintParts:
    """Compute the fingerprint and return it alongside its normalised inputs."""
    norm_employer = normalise_employer(employer)
    norm_title = normalise_title(title)

    if is_remote:
        location = REMOTE_TOKEN
    else:
        country = parse_country(location_raw)
        location = country if country else UNKNOWN_TOKEN

    payload = "|".join((norm_employer, norm_title, location))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    return FingerprintParts(
        employer=norm_employer,
        title=norm_title,
        location=location,
        digest=digest,
    )
