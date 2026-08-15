from __future__ import annotations

from urllib.parse import urlparse

from .models import EvidenceItem

_TRUSTED_HOST_FRAGMENTS = (
    "opentargets.org",
    "ebi.ac.uk",
    "europepmc.org",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "uniprot.org",
    "reactome.org",
    "clinicaltrials.gov",
    "doi.org",
)

_BLOCKED_HOST_FRAGMENTS = (
    "example.com",
    "example.org",
    "invalid",
    "localhost",
    "127.0.0.1",
)


def _host_ok(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(str(url))
    except Exception:
        return False, "source_url_unparseable"
    if parsed.scheme not in {"http", "https"}:
        return False, "source_url_scheme_invalid"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "source_url_host_missing"
    if any(bad in host for bad in _BLOCKED_HOST_FRAGMENTS):
        return False, "source_url_placeholder_host"
    return True, host


def verify_evidence_item(item: EvidenceItem) -> EvidenceItem:
    """
    Structural provenance gate (fail closed).
    Accepted items may influence the verdict; rejected items are retained for audit only.
    """
    reasons: list[str] = []

    if not (item.source_name or "").strip():
        reasons.append("source_name_missing")
    if not (item.title or "").strip() or len(item.title.strip()) < 8:
        reasons.append("title_too_short")
    if not (item.summary or "").strip() or len(item.summary.strip()) < 24:
        reasons.append("summary_too_short")
    if not (item.independent_key or "").strip():
        reasons.append("independent_key_missing")

    host_ok, host_detail = _host_ok(str(item.source_url))
    if not host_ok:
        reasons.append(host_detail)
    else:
        trusted = any(frag in host_detail for frag in _TRUSTED_HOST_FRAGMENTS)
        citation = (item.citation or "").strip().lower()
        has_pmid = citation.startswith("pmid") or "pmid:" in citation
        # Allow trusted scientific hosts, or any https source with a PMID citation.
        if not trusted and not has_pmid and not host_detail.endswith(".gov"):
            # Still accept https URLs from other hosts if they look like real documents,
            # but mark reason for audit; product rule: require trusted host OR pmid OR .gov.
            reasons.append("source_host_not_in_allowlist")

    if reasons:
        return item.model_copy(
            update={
                "provenance_status": "rejected",
                "provenance_reason": ",".join(reasons),
            }
        )
    return item.model_copy(
        update={
            "provenance_status": "accepted",
            "provenance_reason": None,
        }
    )


def apply_provenance_gate(items: list[EvidenceItem]) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
    """Return (accepted_for_scoring, rejected_audit_only)."""
    accepted: list[EvidenceItem] = []
    rejected: list[EvidenceItem] = []
    for item in items:
        verified = verify_evidence_item(item)
        if verified.provenance_status == "accepted":
            accepted.append(verified)
        else:
            rejected.append(verified)
    return accepted, rejected
