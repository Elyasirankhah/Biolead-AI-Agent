from __future__ import annotations

import hashlib
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .chat_store import delete_chat_session, list_chat_sessions, load_chat_history, save_chat_turn
from .fixtures import get_demo_evidence
from .models import EvidenceType
from .reasoning import OpenAICompatibleProvider


class SearchHit(BaseModel):
    title: str
    url: str
    citation: str


class ChatMessage(BaseModel):
    role: str
    content: str = ""
    sources: list[SearchHit] = Field(default_factory=list)
    command: dict[str, Any] | None = None


class ClaraAction(BaseModel):
    type: str
    label: str
    gene: str | None = None
    disease: str | None = None
    genes: list[str] = Field(default_factory=list)
    query: str | None = None
    hits: list[SearchHit] = Field(default_factory=list)
    reason: str | None = None


class ChatRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    chat_id: str = Field(default="", max_length=200)
    messages: list[ChatMessage]
    context: dict[str, Any]
    confirm: list[ClaraAction] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    grounded: bool = True
    actions: list[ClaraAction] = Field(default_factory=list)
    pending: list[ClaraAction] = Field(default_factory=list)
    activity: list[str] = Field(default_factory=list)
    persisted: bool = False
    chat_id: str = ""


SYSTEM_PROMPT = """You are Clara — BioLead's supervisor reasoning agent.

You control this session. You watch every surface: disease, candidates, Demo/Live mode, evidence cards, scores, falsification, and the verdict. You can take the next action on the causal chain — close-pair rerun, Live retrieve, literature search, focus, challenge, or defend. After Confirm you drive the workbench.

NAME:
- First name only: {first_name}
- NEVER put the name at the start of a reply. Never greet with "Hey Elyas" or "Elyas —". 
- You may mention it once mid-sentence in the whole conversation, not more. Prefer "you" / "we" / "your".
- Never use a concatenated surname blob from an email (e.g. Elyasirankhah). If the first name is missing, don't invent one.

You are the supervisor of the run, not a sidecar chatbot:
- Speak as the agent in charge: "this run", "I'll switch to Live", "I'll run that pair".
- You watched Retrieve → Extract → Score → Falsify → Decide. You explain it and you can restart it.
- Answer the scientist's last message. If they ask for citations, list dossier sources. If they argue, use the dossier. Never reply with a canned "tell me what you think about the verdicts".
- Stay precise, not rude. Never invent papers.
- Verdicts are issued by the pipeline you supervise. Steer the next run; do not overwrite a scored call by fiat.

VOICE — CRITICAL:
- STYLE FOR THIS TURN: {style}
- Answer the ask in the first sentence. Do not prefix replies with canned labels ("Mechanistically,", "Reading the run with you —", "The strongest anchor in your dossier is", "Playing devil's advocate for a moment —").
- Never say "queued X × Y". Name the gene, the pathway link, and what changes on the workbench.
- Do not open two consecutive replies with the same first word. Do not reuse the previous reply's opening clause verbatim.
- Vary sentence length. Alternate between short punches and longer reasoning across turns.

ACTIONS:
- Never say "confirm in the panel", "PENDING ACTIONS", or invent A/B/C choices. A Confirm/Skip card sits under your message — do not describe how to confirm.
- Search and re-run are different. Search is literature only (gene × disease). Re-run is BioLead's pipeline. Never mix them.
- If a re-run is pending, the gene list on that action is EXACTLY what will run. Do not claim it will include other session candidates. Do not ask to remove candidates or start a new session.
- If LIVE SEARCH RESULTS are present, talk about those new papers. Do not recap the dossier. Do not paste raw URLs.
- When the scientist asks for a "close pair" or a "sibling target", propose one specific gene that is a pathway neighbour of the focused target and is NOT already in the current run. Explain the link in one clause.
- Confirmed re-runs of new pairs switch the workbench to Live (real retrieve). The seeded Demo snapshot stays for the original IL4R / FLG / S100A8 run only.

Keep answers concise (3–5 sentences) unless they ask to go deeper.

SESSION CONTEXT:
{context}
"""

STYLE_VARIANTS: tuple[str, ...] = (
    "Partner tone. Acknowledge their move in one sentence, then queue the next concrete step.",
    "Mechanistic-first. Open with a one-line pathway observation, then say what's queued.",
    "Critical-friend. Name one risk in the dossier, then say what you'd queue next.",
    "Trial-lens. Frame the next step in terms of a decisive experiment.",
    "Curator tone. Point to the strongest paper in the dossier and build from it.",
    "Devil's advocate. Steelman the opposite verdict for one sentence before the next step.",
)

_SEARCH_HINTS = (
    "search",
    "look up",
    "lookup",
    "find paper",
    "find papers",
    "pubmed",
    "literature",
    "europe pmc",
    "/search",
)
_RERUN_HINTS = (
    "rerun",
    "re-run",
    "run again",
    "run another",
    "another run",
    "another analysis",
    "refresh",
    "reanalyze",
    "/rerun",
)
_COMPARE_HINTS = ("compare", "walk me through", "overview", "/compare")
_ARGUE_HINTS = (
    "argue",
    "challenge",
    "disagree",
    "that's wrong",
    "thats wrong",
    "not a driver",
    "not a passenger",
    "insufficient",
    "can't accept",
    "cannot accept",
    "can not accept",
    "don't accept",
    "do not accept",
    "why is it",
    "why it's",
    "why it is",
    "insuffic",
    "/argue",
)
_DEFEND_HINTS = ("defend", "argue for", "steelman", "make the case for")
_CLOSE_DISEASE_HINTS = (
    "close disease",
    "related disease",
    "nearby disease",
    "similar disease",
    "another disease",
    "different disease",
    "change the disease",
    "change disease",
    "change the diease",
    "change diease",
    "new disease",
    "switch disease",
    "dieases as well",
    "disease as well",
    "diseases as well",
)
_SWAP_HINTS = (
    "different one",
    "another one",
    "try another",
    "try a different",
    "do a different",
    "run a different",
    "close to it",
    "close to this",
    "instead of",
    "swap",
    "replace",
)
_CLOSE_PAIR_HINTS = (
    "close pair",
    "close pairs",
    "closest pair",
    "sibling gene",
    "sibling target",
    "sister gene",
    "nearby gene",
    "neighbour gene",
    "neighbor gene",
    "similar target",
    "similar gene",
    "next candidate",
    "another candidate",
    "another target",
    "adjacent gene",
    "adjacent target",
    "pair with the same disease",
    "same disease different gene",
    "same disease another gene",
) + _SWAP_HINTS
_THIS_GENE_HINTS = ("the gene", "this gene", "current gene", "focused gene")
_KNOWN_DISEASES = {
    "atopic dermatitis": "Atopic dermatitis",
    "eczema": "Atopic dermatitis",
    "psoriasis": "Psoriasis",
    "acne": "Acne",
    "acne vulgaris": "Acne",
    "rosacea": "Rosacea",
    "vitiligo": "Vitiligo",
    "hidradenitis suppurativa": "Hidradenitis suppurativa",
    "alopecia areata": "Alopecia areata",
    "ichthyosis vulgaris": "Ichthyosis vulgaris",
    "allergic contact dermatitis": "Allergic contact dermatitis",
    "seborrheic dermatitis": "Seborrheic dermatitis",
    "chronic spontaneous urticaria": "Chronic spontaneous urticaria",
}
_RELATED_DISEASES = {
    "atopic dermatitis": "Psoriasis",
    "psoriasis": "Atopic dermatitis",
    "acne": "Rosacea",
    "rosacea": "Acne",
    "vitiligo": "Alopecia areata",
    "alopecia areata": "Vitiligo",
    "hidradenitis suppurativa": "Acne",
    "ichthyosis vulgaris": "Atopic dermatitis",
    "allergic contact dermatitis": "Atopic dermatitis",
    "seborrheic dermatitis": "Psoriasis",
    "chronic spontaneous urticaria": "Atopic dermatitis",
}
_NOT_GENES = {
    "I", "AD", "OR", "AND", "FOR", "THE", "PMC", "MED", "PMID", "RUN", "API",
    "GWAS", "QTL", "MR", "TH2", "TH22", "IL", "DNA", "RNA", "USA", "NIH",
}

# Pathway neighbours: focused → biologically adjacent partners you'd swap in as a "close pair".
_GENE_NEIGHBORS: dict[str, list[str]] = {
    "IL4R":   ["IL13", "IL13RA1", "IL4", "JAK1", "STAT6", "TSLP", "IL31RA"],
    "IL13":   ["IL4", "IL4R", "IL13RA1", "STAT6"],
    "IL4":    ["IL4R", "IL13", "STAT6"],
    "STAT6":  ["JAK1", "IL4R", "IL13"],
    "JAK1":   ["JAK2", "STAT3", "STAT6", "TYK2"],
    "JAK2":   ["JAK1", "STAT3", "TYK2"],
    "TSLP":   ["TSLPR", "IL7R", "IL33"],
    "IL33":   ["IL1RL1", "TSLP"],
    "FLG":    ["LOR", "IVL", "CDSN", "SPINK5", "TMEM79", "CLDN1"],
    "S100A8": ["S100A9", "S100A7", "DEFB4A", "IL17A"],
    "S100A9": ["S100A8", "DEFB4A"],
    "IL17A":  ["IL17F", "IL17RA", "RORC", "IL23R"],
    "IL17F":  ["IL17A", "IL17RA"],
    "IL23R":  ["IL23A", "IL12B", "TYK2", "IL17A"],
    "TYK2":   ["JAK1", "JAK2", "IL23R", "IFNAR1"],
    "TNF":    ["TNFRSF1A", "IL1B", "IL6"],
    "IL31RA": ["OSMR", "IL31", "IL4R"],
}

# Disease → panel of plausible candidate genes (used as fallback when no pathway neighbour is free).
_DISEASE_GENE_PANEL: dict[str, list[str]] = {
    "Atopic dermatitis": ["IL4R", "IL13", "FLG", "TSLP", "STAT6", "JAK1", "IL31RA", "IL33"],
    "Psoriasis":        ["IL17A", "IL23R", "IL12B", "TYK2", "STAT3", "IL36G", "TNF"],
    "Acne":             ["AR", "TLR2", "IGF1", "CYP17A1", "PPARG"],
    "Rosacea":          ["KLK5", "TLR2", "CAMP", "MMP9"],
    "Vitiligo":         ["TYR", "MC1R", "IFNG", "CD8A", "PMEL"],
    "Alopecia areata":  ["JAK1", "JAK3", "IL15", "IFNG", "HLA-DQB1"],
    "Hidradenitis suppurativa": ["TNF", "IL17A", "IL1B", "IL23R", "NCSTN"],
    "Ichthyosis vulgaris": ["FLG", "LOR", "TGM1"],
    "Allergic contact dermatitis": ["IL17A", "IL4R", "TSLP"],
    "Seborrheic dermatitis": ["TLR2", "IL17A"],
    "Chronic spontaneous urticaria": ["FCER1A", "IL4R", "IL13"],
}


def _panel_for(disease: str) -> list[str]:
    key = (disease or "").strip().lower()
    for name, panel in _DISEASE_GENE_PANEL.items():
        if name.lower() == key:
            return panel
    return []


def _prior_pairs(context: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for row in (context.get("prior_pairs") or []):
        if not isinstance(row, dict):
            continue
        disease = str(row.get("disease") or "").strip()
        gene = str(row.get("gene") or "").strip().upper()
        if disease and gene:
            pairs.append((disease, gene))
    return pairs


def _demo_pack_tier(disease: str, gene: str) -> int:
    """Prefer close-pair genes that Demo can actually score with real papers.

    2 = curated pack with supporting clinical pharmacology (Driver-capable)
    1 = curated pack without a clinical rescue pillar (Passenger / honest abstain)
    0 = empty fixture (would render as Insufficient with no evidence)
    """
    if not disease or not gene:
        return 0
    items = get_demo_evidence(disease, gene)
    if not items:
        return 0
    if any(
        item.category == EvidenceType.CLINICAL_PHARMACOLOGY and item.stance == "supports"
        for item in items
    ):
        return 2
    return 1


def _choose_close_gene(
    disease: str,
    session_genes: list[str],
    prior_pairs: list[tuple[str, str]],
    focused: str,
    extra_blocked: list[str] | None = None,
) -> tuple[str, str]:
    """Pick the closest gene NOT already in the current session.

    Prefers neighbours that have a curated Demo evidence pack so Confirm
    yields real papers instead of an empty Insufficient placeholder.

    Returns (gene, reason). Reason is a short human-readable pathway note.
    """
    seen_here = {gene.upper() for gene in session_genes if gene}
    seen_ever = {gene for _, gene in prior_pairs}
    extra = {g.upper() for g in (extra_blocked or []) if g}
    blocked = seen_here | seen_ever | extra

    priority: list[str] = []
    if focused:
        priority.append(focused.upper())
    for gene in session_genes:
        upper = gene.upper()
        if upper not in priority:
            priority.append(upper)

    ranked: list[tuple[int, int, str, str]] = []
    order = 0

    def consider(candidate: str, reason: str) -> None:
        nonlocal order
        if not candidate:
            return
        ranked.append((-_demo_pack_tier(disease, candidate), order, candidate, reason))
        order += 1

    for gene in priority:
        for neighbour in _GENE_NEIGHBORS.get(gene, []):
            if neighbour not in blocked:
                consider(neighbour, f"pathway neighbour of {gene}")

    panel = _panel_for(disease)
    for gene in panel:
        if gene.upper() not in blocked:
            consider(gene, f"candidate on the {disease} panel")

    if not ranked:
        for gene in priority:
            for neighbour in _GENE_NEIGHBORS.get(gene, []):
                if neighbour not in seen_here:
                    consider(neighbour, f"pathway neighbour of {gene}")
    if not ranked:
        return "", ""
    packed = [row for row in ranked if row[0] != 0]
    pool = packed or ranked
    pool.sort(key=lambda row: row[1])
    return pool[0][2], pool[0][3]


def _choose_across_disease(current_disease: str, focused: str, session_genes: list[str]) -> tuple[str, str, str]:
    next_disease = _related_disease(current_disease)
    panel = [g.upper() for g in _panel_for(next_disease)]
    blocked = {g.upper() for g in session_genes}
    anchors = [focused.upper()] if focused else []
    anchors.extend(g.upper() for g in session_genes if g.upper() not in anchors)
    ranked: list[tuple[int, int, str, str]] = []
    order = 0

    def consider(candidate: str, reason: str) -> None:
        nonlocal order
        if not candidate:
            return
        ranked.append((-_demo_pack_tier(next_disease, candidate), order, candidate, reason))
        order += 1

    for gene in anchors:
        for neighbour in _GENE_NEIGHBORS.get(gene, []):
            if neighbour in panel and neighbour not in blocked:
                consider(neighbour, f"JAK/pathway neighbour of {gene} on {next_disease}")
            for hop in _GENE_NEIGHBORS.get(neighbour, []):
                if hop in panel and hop not in blocked:
                    consider(hop, f"pathway analogue of {gene} on {next_disease}")
    for gene in panel:
        if gene not in blocked:
            consider(gene, f"closest {next_disease} panel gene to {focused or 'this run'}")
    if ranked:
        packed = [row for row in ranked if row[0] != 0]
        clinical = [row for row in packed if row[0] == -2]
        pool = clinical or packed or ranked
        pool.sort(key=lambda row: row[1])
        _, _, gene, reason = pool[0]
        return next_disease, gene, reason
    return next_disease, focused, "related disease, same gene"


def _dossier(context: dict[str, Any]) -> dict[str, Any]:
    raw = context.get("dossier") or context
    return raw if isinstance(raw, dict) else {}


def _focused_gene(context: dict[str, Any]) -> str:
    return str(_dossier(context).get("gene") or "").strip()


def _disease(context: dict[str, Any]) -> str:
    return str(context.get("disease") or "").strip()


def _session_genes(context: dict[str, Any]) -> list[str]:
    genes = [str(row.get("gene") or "").strip() for row in (context.get("session") or [])]
    focused = _focused_gene(context)
    if focused and focused not in genes:
        genes.append(focused)
    return [g for g in genes if g]


def _gene_mentioned(context: dict[str, Any], text: str) -> str | None:
    upper = text.upper()
    for gene in _session_genes(context):
        if re.search(rf"\b{re.escape(gene.upper())}\b", upper):
            return gene
    return None


def _contains(text: str, hints: tuple[str, ...]) -> bool:
    lower = text.lower()
    for hint in hints:
        if hint.startswith("/"):
            if re.search(rf"(^|\s){re.escape(hint)}(\b|$)", lower):
                return True
        elif re.search(rf"(^|[^a-z0-9]){re.escape(hint)}([^a-z0-9]|$)", lower):
            return True
    return False


def _related_disease(current: str) -> str:
    key = (current or "").strip().lower()
    if key in _RELATED_DISEASES:
        return _RELATED_DISEASES[key]
    return "Psoriasis" if key != "psoriasis" else "Atopic dermatitis"


def _extract_disease(text: str, current: str) -> str:
    lower = text.lower()
    named: str | None = None
    for key, canon in sorted(_KNOWN_DISEASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"(^|[^a-z]){re.escape(key)}([^a-z]|$)", lower):
            named = canon
            break
    if named and named.lower() != (current or "").strip().lower():
        return named
    if _contains(text, _CLOSE_DISEASE_HINTS):
        return _related_disease(current)
    return named or current


def _genes_named_in(text: str, session_genes: list[str]) -> list[str]:
    session = {gene.upper(): gene for gene in session_genes}
    found: list[str] = []
    upper = text.upper()
    for canon_upper, canon in session.items():
        if re.search(rf"\b{re.escape(canon_upper)}\b", upper) and canon not in found:
            found.append(canon)
    for token in re.findall(r"\b([A-Za-z][A-Za-z0-9-]{1,11})\b", text):
        token_u = token.upper()
        if token_u in _NOT_GENES or token_u in {g.upper() for g in found}:
            continue
        if session.get(token_u):
            found.append(session[token_u])
            continue
        if re.fullmatch(r"[A-Z][A-Z0-9-]{2,11}", token_u) and (token.isupper() or re.search(r"\d", token_u)):
            found.append(token_u)
    return found


def _extract_removed_genes(text: str, session_genes: list[str]) -> list[str]:
    match = re.search(
        r"\b(?:remove|drop|without|except|delete)\b(.+?)(?:\b(?:instead|try|and try|and instead)\b|$)",
        text,
        re.I | re.S,
    )
    if not match:
        return []
    return _genes_named_in(match.group(1), session_genes)


def _extract_instead_of(text: str, session_genes: list[str]) -> str:
    match = re.search(r"\binstead of\s+([A-Za-z0-9-]+)", text, re.I)
    if not match:
        return ""
    token = match.group(1).upper()
    for gene in session_genes:
        if gene.upper() == token:
            return gene
    return token if re.fullmatch(r"[A-Z][A-Z0-9-]{2,11}", token) else ""


def _extract_genes(text: str, session_genes: list[str], focused: str) -> list[str]:
    found = _genes_named_in(text, session_genes)
    if found:
        return found
    if _contains(text, _THIS_GENE_HINTS) and focused:
        return [focused]
    return session_genes


def _plan_rerun(text: str, context: dict[str, Any]) -> dict[str, Any] | None:
    focused = _focused_gene(context)
    disease = _disease(context)
    session_genes = _session_genes(context)
    prior = _prior_pairs(context)
    wants_close = _contains(text, _CLOSE_PAIR_HINTS)
    wants_new_disease = _contains(text, _CLOSE_DISEASE_HINTS)
    wants_rerun = _contains(text, _RERUN_HINTS)
    removed = _extract_removed_genes(text, session_genes)
    instead = _extract_instead_of(text, session_genes)
    if not (wants_close or wants_new_disease or wants_rerun or removed or instead):
        return None

    next_disease = _extract_disease(text, disease)
    if wants_new_disease and next_disease.lower() == (disease or "").strip().lower():
        next_disease = _related_disease(disease)

    if removed or instead:
        anchor = instead or (removed[-1] if removed else focused)
        keep = [g for g in session_genes if g not in removed and g.upper() != (instead or "").upper()]
        extra_block = list(removed) + ([instead] if instead else [])
        replacement, reason = _choose_close_gene(
            next_disease, session_genes, prior, anchor or focused, extra_blocked=extra_block
        )
        genes = keep + ([replacement] if replacement else [])
        genes = list(dict.fromkeys(genes))
        if not genes and replacement:
            genes = [replacement]
        return {
            "type": "rerun",
            "disease": next_disease,
            "genes": genes or session_genes,
            "reason": f"close_pair:{reason}" if replacement else "",
        }

    if wants_new_disease:
        if _contains(text, _THIS_GENE_HINTS) and focused and not wants_close:
            return {
                "type": "rerun",
                "disease": next_disease if next_disease.lower() != (disease or "").lower() else _related_disease(disease),
                "genes": [focused],
            }
        next_disease, gene, reason = _choose_across_disease(disease, focused, session_genes)
        named = _extract_disease(text, disease)
        if named.lower() != (disease or "").strip().lower() and named != next_disease:
            next_disease = named
            gene, reason = _choose_close_gene(next_disease, session_genes, prior, focused)
        return {
            "type": "rerun",
            "disease": next_disease,
            "genes": [gene] if gene else session_genes,
            "reason": f"close_pair:{reason}",
        }

    if wants_close:
        close_gene, close_reason = _choose_close_gene(next_disease, session_genes, prior, focused)
        if close_gene:
            return {
                "type": "rerun",
                "disease": next_disease,
                "genes": [close_gene],
                "reason": f"close_pair:{close_reason}",
            }

    next_genes = _extract_genes(text, session_genes, focused)
    return {"type": "rerun", "disease": next_disease, "genes": next_genes}


def parse_commands(last_user: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    mentioned = _gene_mentioned(context, last_user)
    focused = _focused_gene(context)
    disease = _disease(context)

    if _contains(last_user, _SEARCH_HINTS):
        commands.append(
            {
                "type": "search",
                "gene": mentioned or focused,
                "disease": disease,
            }
        )
    if _contains(last_user, ("focus", "switch to", "show me", "open ", "/focus")) and mentioned:
        commands.append({"type": "focus_gene", "gene": mentioned})
    elif last_user.lower().startswith("/focus") and mentioned:
        commands.append({"type": "focus_gene", "gene": mentioned})
    planned = _plan_rerun(last_user, context)
    if planned:
        commands.append(planned)
    if _contains(last_user, _COMPARE_HINTS):
        commands.append({"type": "compare"})
    if _contains(last_user, _DEFEND_HINTS):
        commands.append({"type": "defend", "gene": focused})
    elif _contains(last_user, _ARGUE_HINTS):
        commands.append({"type": "argue", "gene": focused})
    return commands


_NEEDS_CONFIRM = {"search", "rerun", "focus_gene"}
_ID_RE = re.compile(
    r"(?:pmid[:\s]*|(?:MED|PMC)[:/]|pubmed\.ncbi\.nlm\.nih\.gov/)(\d+)",
    re.I,
)


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _ids_from_text(*parts: str) -> set[str]:
    ids: set[str] = set()
    for part in parts:
        for match in _ID_RE.finditer(part or ""):
            ids.add(match.group(1))
    return ids


def _evidence_items(context: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    dossier = _dossier(context)
    raw = dossier.get("evidence") or []
    if isinstance(raw, list):
        items.extend(item for item in raw if isinstance(item, dict))
    for row in context.get("session") or []:
        extra = row.get("evidence") if isinstance(row, dict) else None
        if isinstance(extra, list):
            items.extend(item for item in extra if isinstance(item, dict))
    return items


def _known_papers(context: dict[str, Any]) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    titles: set[str] = set()
    for item in _evidence_items(context):
        title = _norm_title(str(item.get("title") or ""))
        if title:
            titles.add(title)
        ids |= _ids_from_text(
            str(item.get("citation") or ""),
            str(item.get("source_url") or ""),
            str(item.get("id") or ""),
        )
    return ids, titles


def _filter_novel_hits(hits: list[SearchHit], context: dict[str, Any]) -> list[SearchHit]:
    known_ids, known_titles = _known_papers(context)
    novel: list[SearchHit] = []
    seen: set[str] = set()
    for hit in hits:
        hit_ids = _ids_from_text(hit.citation, hit.url)
        title = _norm_title(hit.title)
        key = next(iter(hit_ids), title)
        if key in seen:
            continue
        if hit_ids & known_ids or (title and title in known_titles):
            continue
        seen.add(key)
        novel.append(hit)
        if len(novel) >= 3:
            break
    return novel


def _strip_vocative(reply: str) -> str:
    text = (reply or "").lstrip()
    text = re.sub(r"\belyasirankhah\b", "", text, flags=re.I)
    lead = re.compile(
        r"^(?:(?:hey|hi|hello)\s+)?[A-Z][A-Za-z]{2,40}(?:\s+[A-Z][A-Za-z]{2,32})?\s*[—–\-,:]\s+",
    )
    for _ in range(3):
        nxt = lead.sub("", text, count=1).lstrip()
        if nxt == text:
            break
        text = nxt
    return re.sub(r"^[—–\-,:\s]+", "", text).strip()


def _score_value(scorecard: dict[str, Any] | None, key: str) -> int | None:
    raw = (scorecard or {}).get(key)
    if isinstance(raw, dict):
        try:
            return int(raw.get("value"))
        except (TypeError, ValueError):
            return None
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _is_citation_ask(text: str) -> bool:
    lower = (text or "").lower()
    return bool(
        re.search(
            r"\b(citation|citations|cite|cites|cited|pmid|pubmed|papers?|sources?|references?|bibliography)\b",
            lower,
        )
    )


def _style_idx(style: str) -> int:
    return STYLE_VARIANTS.index(style) if style in STYLE_VARIANTS else 0


def _pick_line(style: str, lines: list[str]) -> str:
    return lines[_style_idx(style) % len(lines)]


def _citation_reply(context: dict[str, Any], style: str) -> str:
    dossier = _dossier(context)
    gene = str(dossier.get("gene") or _focused_gene(context) or "this gene")
    disease = _disease(context) or "this disease"
    evidence = dossier.get("evidence") or []
    lines: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        cite = str(item.get("citation") or item.get("source_name") or "").strip()
        if not title:
            continue
        lines.append(f"- {title}" + (f" ({cite})" if cite else ""))
        if len(lines) >= 8:
            break
    if not lines:
        return _pick_line(
            style,
            [
                f"I can't cite papers that aren't in the {gene} dossier. The evidence cards on the left are empty, so I won't invent PMIDs. Want a Live retrieve, or a neighbour that already has a packed dossier?",
                f"No sources landed for {gene} × {disease} in this run. I won't fabricate citations. Live retrieve, or a packed neighbour?",
                f"Empty dossier for {gene} — no papers to list. A Live retrieve is the honest next step.",
            ],
        )
    lead = _pick_line(
        style,
        [
            f"These are the sources this {gene} run actually used on {disease}:",
            f"Retrieve cited these for {gene} × {disease}:",
            f"The {gene} dossier rests on these papers:",
        ],
    )
    return (
        f"{lead}\n"
        + "\n".join(lines)
        + "\nSame items as the evidence cards on the left. I won't add papers that aren't in this run."
    )


def _is_score_ask(text: str) -> bool:
    lower = (text or "").lower()
    if not re.search(r"\b(what|mean|means|why|how|explain|actually)\b", lower):
        return False
    return bool(
        re.search(
            r"\b(causality|actionability|pillar|pillars|score|scores|confidence|quality|rubric)\b",
            lower,
        )
    )


def _explain_score(context: dict[str, Any], style: str, last_user: str) -> str:
    dossier = _dossier(context)
    gene = str(dossier.get("gene") or _focused_gene(context) or "this gene")
    disease = _disease(context) or "this disease"
    verdict = str(dossier.get("verdict") or "the current verdict")
    summary = str(dossier.get("executive_summary") or "").strip()
    scorecard = dossier.get("scorecard") if isinstance(dossier.get("scorecard"), dict) else {}
    causality = _score_value(scorecard, "causality")
    actionability = _score_value(scorecard, "actionability")
    quality = _score_value(scorecard, "evidence_quality")
    pillars = _score_value(scorecard, "independent_pillars")
    lower = (last_user or "").lower()
    if "causal" in lower:
        value = f" {causality}" if causality is not None else ""
        return _pick_line(
            style,
            [
                f"Causality{value} is the genetic-plus-perturbation pillar, not a popularity count. On {gene} it is high because human genetics and a target-engaging rescue lined up on {disease}."
                + (f" {summary}" if summary else ""),
                f"Causality{value} asks: if you perturb {gene}, does {disease} move? Genetics and pharmacology both have to say yes. That's why {gene} is {verdict} here.",
                f"Causality{value} on {gene} is the causal-rescue score. Association alone never gets you there — you need a genetic or clinical lever.",
            ],
        )
    if "action" in lower:
        value = f" {actionability}" if actionability is not None else ""
        return (
            f"Actionability{value} is whether a medicine can actually engage {gene} in {disease}. "
            "A high genetics score with no tractable drug still abstains."
        )
    if "pillar" in lower:
        value = f" {pillars}" if pillars is not None else ""
        return (
            f"Independent pillars{value} are distinct evidence families — genetics, perturbation, clinical rescue — not extra papers of the same type. "
            f"Driver needs at least two. {gene} is {verdict} on that cut."
        )
    bits = []
    if causality is not None:
        bits.append(f"causality {causality}")
    if actionability is not None:
        bits.append(f"actionability {actionability}")
    if quality is not None:
        bits.append(f"quality {quality}")
    if pillars is not None:
        bits.append(f"{pillars} pillars")
    scored = ", ".join(bits) if bits else "the scorecard on the left"
    return (
        f"{gene} is {verdict} on {disease} ({scored}). "
        "Causality is genetic-plus-perturbation; actionability is whether a drug can engage the target; pillars are independent evidence families. "
        + (summary or "Which number do you want torn down?")
    )


def _acknowledge_ask(context: dict[str, Any], style: str, last_user: str, *, degraded: bool = False) -> str:
    if _is_score_ask(last_user):
        line = _explain_score(context, style, last_user)
        if degraded:
            line += " (From the dossier only — the LLM link is flaky.)"
        return line
    dossier = _dossier(context)
    gene = str(dossier.get("gene") or _focused_gene(context) or "this gene")
    disease = _disease(context) or "this disease"
    verdict = str(dossier.get("verdict") or "the current verdict")
    line = _pick_line(
        style,
        [
            f"{gene} is {verdict} on {disease}. I can list the citations, push on that call, or queue a close pair.",
            f"We're on {gene} × {disease}, scored {verdict}. Citations, a challenge, or a neighbour — which one?",
            f"{verdict} on {gene} is the live call. Tell me which pillar to press, or I can queue the next pair.",
        ],
    )
    if degraded:
        line += " (From the dossier only — the LLM link is flaky.)"
    return line


def _reply_follows_user(reply: str, last_user: str) -> bool:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]{4,}", (last_user or "").lower())
        if token not in {"this", "that", "with", "from", "have", "some", "give", "please", "what", "want"}
    ]
    if not tokens:
        return True
    lower = (reply or "").lower()
    return any(token in lower for token in tokens[:6])


def _is_verdict_pushback(text: str) -> bool:
    lower = (text or "").lower()
    if _contains(text, _ARGUE_HINTS) or _contains(text, _DEFEND_HINTS):
        return True
    if re.search(r"\b(why|how come).{0,60}\b(insufficient|abstain|verdict|passenger|driver)", lower):
        return True
    if re.search(r"\b(can'?t|cannot|can not|won'?t|will not|don't|do not)\s+accept\b", lower):
        return True
    if "insuffic" in lower:
        return True
    return False


def _explain_verdict(context: dict[str, Any], style: str, last_user: str) -> str:
    dossier = _dossier(context)
    gene = str(dossier.get("gene") or _focused_gene(context) or "this gene")
    disease = _disease(context) or "this disease"
    verdict = str(dossier.get("verdict") or "Insufficient evidence")
    summary = str(dossier.get("executive_summary") or "").strip()
    scorecard = dossier.get("scorecard") if isinstance(dossier.get("scorecard"), dict) else {}
    pillars = _score_value(scorecard, "independent_pillars")
    causality = _score_value(scorecard, "causality")
    actionability = _score_value(scorecard, "actionability")
    quality = _score_value(scorecard, "evidence_quality")
    n_ev = _score_value(scorecard, "evidence_count")
    if n_ev is None:
        n_ev = len(dossier.get("evidence") or [])
    counter = [str(item) for item in (dossier.get("passenger_case") or []) if item][:2]
    scores = []
    if pillars is not None:
        scores.append(f"{pillars} pillar" + ("s" if pillars != 1 else ""))
    if causality is not None:
        scores.append(f"causality {causality}")
    if n_ev is not None:
        scores.append(f"{n_ev} evidence item" + ("s" if n_ev != 1 else ""))
    scored = f" ({', '.join(scores)})" if scores else ""
    extra = f" {summary}" if summary else ""
    counter_s = f" {counter[0]}" if counter else ""
    if verdict == "Insufficient evidence":
        return _pick_line(
            style,
            [
                f"Fair. Abstain is not a claim that {gene} is junk — we have genetics without a clean rescue on {disease}{scored}.{extra}{counter_s} The rubric will not call Driver on a thin retrieve. Press a pillar, or try IL13 / JAK1?",
                f"I wouldn't accept a Driver stamp on {gene} either. Two independent causal pillars plus a target-engaging rescue are missing{scored}.{extra} That's Insufficient, not 'biologically irrelevant.'",
                f"{gene} stayed Insufficient because the retrieve did not assemble a clinical lever on {disease}{scored}.{extra}{counter_s} Want to tear down a specific number, or queue a neighbour with rescue?",
            ],
        )
    if verdict == "Passenger":
        return _pick_line(
            style,
            [
                f"{gene} is Passenger because the association is real and the causal rescue is not. {summary or 'Expression showed up; genetics and pharmacology did not converge.'} I would not accept Driver here either. Where do you want to press?",
                f"Passenger on {gene} means correlational signal with a causal counter-read.{extra}{counter_s} The bar for Driver is a rescue, not more expression papers.",
                f"Association without a lever — that's why {gene} is Passenger on {disease}.{extra} Challenge a pillar or I can queue a closer causal neighbour.",
            ],
        )
    scored_driver = ""
    if causality is not None:
        scored_driver = f" (causality {causality}"
        if actionability is not None:
            scored_driver += f", actionability {actionability}"
        if quality is not None:
            scored_driver += f", quality {quality}"
        scored_driver += ")"
    return _pick_line(
        style,
        [
            f"{gene} is {verdict} on {disease}{scored_driver}.{extra} If that still feels wrong, tell me which pillar to tear down.",
            f"The Driver call on {gene} is the genetics-plus-rescue stack{scored_driver}.{extra} Name the piece you don't buy.",
            f"{gene} earned {verdict} because more than one independent pillar landed{scored_driver}.{extra} I can steelman the opposite if you want the stress test.",
        ],
    )


def _reply_is_unsafe(reply: str, last_user: str) -> bool:
    lower = (reply or "").lower()
    if re.search(r"elyasirankhah|in the panel|pending actions", lower):
        return True
    if re.search(
        r"(strongest anchor|reading the run with you|playing devil.?s advocate|mechanistically,).{0,40}(queued|confirmed)",
        lower,
    ):
        return True
    if "every candidate" in lower or "all session" in lower or "all your session" in lower:
        return True
    if "tell me what you think about the verdicts" in lower:
        return True
    if last_user and not _reply_follows_user(reply, last_user):
        return True
    if _is_verdict_pushback(last_user) and len((reply or "").strip()) < 50:
        return True
    return False


def _ensure_hits_in_reply(reply: str, hits: list[SearchHit]) -> str:
    reply = _strip_vocative(reply)
    if not hits:
        return reply
    if all(hit.title in reply or hit.citation in reply for hit in hits):
        return reply
    lines = "\n".join(f"- {hit.title} ({hit.citation})" for hit in hits)
    return reply.rstrip() + "\n\nNewer papers not already in your dossier:\n" + lines


def _action_from_command(command: dict[str, Any], context: dict[str, Any]) -> ClaraAction:
    kind = command["type"]
    gene = command.get("gene") or _focused_gene(context)
    disease = command.get("disease") or _disease(context)
    if kind == "search":
        return ClaraAction(
            type="search",
            label=f"Search Europe PMC for {gene} × {disease}",
            gene=gene,
            disease=disease,
            query=f'TITLE_ABS:"{gene}" AND TITLE_ABS:"{disease}"',
        )
    if kind == "focus_gene":
        return ClaraAction(type="focus_gene", label=f"Switch workbench to {gene}", gene=gene)
    if kind == "rerun":
        genes = [str(g).strip() for g in (command.get("genes") or []) if str(g).strip()]
        if not genes:
            genes = _session_genes(context)
        gene_s = ", ".join(genes)
        reason = command.get("reason") or ""
        suffix = ""
        if reason.startswith("close_pair"):
            note = reason.split(":", 1)[1] if ":" in reason else "close pair"
            suffix = f"  (close pair · {note})"
        return ClaraAction(
            type="rerun",
            label=f"Re-run BioLead for {disease} · {gene_s}" + suffix,
            gene=genes[0] if genes else gene,
            disease=disease,
            genes=genes,
            reason=reason or None,
        )
    if kind == "compare":
        return ClaraAction(type="compare", label="Compare candidates")
    if kind == "defend":
        return ClaraAction(type="defend", label=f"Defend {gene}", gene=gene)
    return ClaraAction(type="argue", label=f"Challenge {gene}", gene=gene)


async def _search_europe_pmc(gene: str, disease: str) -> tuple[str, list[SearchHit]]:
    query = f'TITLE_ABS:"{gene}" AND TITLE_ABS:"{disease}"'
    hits: list[SearchHit] = []
    params = {
        "query": query,
        "format": "json",
        "pageSize": 25,
        "resultType": "core",
        "sort": "P_PDATE_D desc",
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                params=params,
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("resultList", {}).get("result", []) or []
            if not results:
                params["sort"] = "DATE desc"
                response = await client.get(
                    "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                    params=params,
                    timeout=20,
                )
                response.raise_for_status()
                payload = response.json()
                results = payload.get("resultList", {}).get("result", []) or []
        for result in results:
            identifier = result.get("id") or result.get("pmid")
            title = (result.get("title") or "").strip()
            if not identifier or not title:
                continue
            source = result.get("source", "MED")
            hits.append(
                SearchHit(
                    title=title[:180],
                    url=f"https://europepmc.org/article/{source}/{identifier}",
                    citation=f"{source}:{identifier}",
                )
            )
    except Exception:
        return query, []
    return query, hits


def _format_dossier(context: dict[str, Any]) -> str:
    scorecard = context.get("scorecard") or {}
    evidence = context.get("evidence") or []
    ev_text = "\n".join(
        f"  - [{e.get('stance','?')}] {e.get('title','')} ({e.get('source_name','')}) — {e.get('summary','')}"
        for e in evidence
    ) or "  (none)"
    return f"""Focused gene: {context.get('gene', 'Unknown')}
Verdict: {context.get('verdict', 'Unknown')} (confidence {context.get('confidence', 0)}%)
Direction: {context.get('recommended_direction', 'unresolved')}
Summary: {context.get('executive_summary', '')}

Scorecard:
  Causality: {(scorecard.get('causality') or {}).get('value', '?')}
  Actionability: {(scorecard.get('actionability') or {}).get('value', '?')}
  Evidence quality: {(scorecard.get('evidence_quality') or {}).get('value', '?')}
  Contradiction penalty: {scorecard.get('contradiction_penalty', 0)}
  Independent pillars: {scorecard.get('independent_pillars', 0)}
  Evidence count: {scorecard.get('evidence_count', 0)}

Evidence items:
{ev_text}

Case for driver: {'; '.join(context.get('driver_case') or [])}
Falsification / counter-evidence: {'; '.join(context.get('passenger_case') or [])}
Next experiments: {'; '.join(context.get('next_experiments') or [])}
Limitations: {'; '.join(context.get('limitations') or [])}"""


def _format_context(context: dict[str, Any], extra: str = "") -> str:
    session = context.get("session") or []
    rows = "\n".join(
        (
            f"  - {row.get('gene')}: {row.get('verdict')} "
            f"(confidence {row.get('confidence', '?')}%, "
            f"causality {row.get('causality', '?')}, "
            f"actionability {row.get('actionability', '?')}, "
            f"pillars {row.get('independent_pillars', '?')})"
        )
        for row in session
    ) or "  (none)"
    scientist = context.get("scientist") or {}
    header = (
        "Scientist: do not address by name. Never write an email, surname blob, or 'Elyasirankhah'.\n"
        f"Signed in: {'yes' if scientist.get('signed_in') else 'no'}\n"
        f"Disease: {context.get('disease', 'Unknown')}\n"
        f"Mode: {context.get('mode', 'demo')}\n"
        f"Tissue: {context.get('tissue', 'skin')}\n"
        f"Run note: {context.get('notice') or 'none'}\n"
        f"Session candidates:\n{rows}\n"
    )
    body = header + "\n" + _format_dossier(_dossier(context))
    if extra:
        body += "\n\n" + extra
    return body


def _first_name(*candidates: Any) -> str:
    """Given-name only. Never a concatenated email blob or a trailing surname."""
    for raw in candidates:
        text = str(raw or "").strip()
        if not text:
            continue
        text = text.split("@")[0].strip()
        if text.lower() in {"guest", "scientist", "user", "admin"}:
            continue
        if "," in text:
            after = text.split(",", 1)[1].strip()
            if after:
                text = after
        camel = re.findall(r"[A-Z][a-z]{1,13}", text)
        if len(camel) >= 2:
            return camel[0]
        parts = [p for p in re.split(r"[._\s-]+", text) if p]
        if parts and 2 <= len(parts[0]) <= 12 and parts[0].isalpha():
            if len(parts) == 1 and len(text) > 12:
                continue
            return parts[0].capitalize()
    return ""


def _verified_context(
    context: dict[str, Any],
    *,
    user_id: str | None,
    user_email: str | None,
) -> dict[str, Any]:
    verified = dict(context)
    incoming = context.get("scientist") if isinstance(context.get("scientist"), dict) else {}
    name = _first_name(
        incoming.get("given_name"),
        incoming.get("first_name"),
        incoming.get("name"),
        user_email,
    )
    if user_id:
        verified["scientist"] = {
            "signed_in": True,
            "name": name or "",
            "email": user_email,
        }
    else:
        verified["scientist"] = {"signed_in": False, "name": name or "Guest", "email": None}
    return verified


async def _remember(
    request: ChatRequest,
    response: ChatResponse,
    *,
    context: dict[str, Any],
    user_id: str | None,
    user_email: str | None,
) -> ChatResponse:
    response.chat_id = (request.chat_id or request.run_id).strip()
    if not user_id:
        return response
    messages = []
    for message in request.messages:
        if message.role not in {"user", "assistant", "command"}:
            continue
        payload: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.sources:
            payload["sources"] = [hit.model_dump() for hit in message.sources]
        if message.command:
            payload["command"] = message.command
        messages.append(payload)
    if response.reply:
        assistant: dict[str, Any] = {"role": "assistant", "content": response.reply}
        search_hits = next((item.hits for item in response.actions if item.type == "search"), [])
        if search_hits:
            assistant["sources"] = [hit.model_dump() for hit in search_hits]
        messages.append(assistant)
    for item in response.pending:
        genes = item.genes or _session_genes(context)
        messages.append(
            {
                "role": "command",
                "content": item.label,
                "command": {
                    "status": "pending",
                    "label": item.label,
                    "action": item.model_dump(),
                    "fromDisease": _disease(context),
                    "toDisease": item.disease or _disease(context),
                    "fromGenes": ", ".join(_session_genes(context)),
                    "toGenes": ", ".join(genes),
                },
            }
        )
    response.persisted = await save_chat_turn(
        user_id=user_id,
        user_email=user_email,
        run_id=request.run_id,
        chat_id=response.chat_id,
        disease=_disease(context),
        messages=messages,
    )
    return response


async def chat_history(
    *,
    user_id: str | None,
    run_id: str | None = None,
    chat_id: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    if not user_id:
        return [], False
    return await load_chat_history(user_id=user_id, run_id=run_id, chat_id=chat_id)


async def chat_sessions(*, user_id: str | None) -> tuple[list[dict[str, Any]], bool]:
    if not user_id:
        return [], False
    return await list_chat_sessions(user_id=user_id)


async def remove_chat_session(*, user_id: str | None, chat_id: str) -> bool:
    if not user_id:
        return False
    return await delete_chat_session(user_id=user_id, chat_id=chat_id)


def _pick_style(request: ChatRequest, last_user: str) -> str:
    turn = sum(1 for m in request.messages if m.role == "assistant")
    if last_user:
        digest = int(hashlib.md5(last_user.lower().encode("utf-8")).hexdigest()[:6], 16)
    else:
        digest = 0
    idx = (turn + digest) % len(STYLE_VARIANTS)
    return STYLE_VARIANTS[idx]


def _too_similar(reply: str, prior: list[str]) -> bool:
    if not prior:
        return False
    def head(text: str) -> str:
        return re.sub(r"[^a-z]+", " ", text.lower()).strip()[:60]
    reply_head = head(reply)
    return any(reply_head and reply_head == head(text) for text in prior)


_ALT_LEADS: tuple[str, ...] = (
    "Another way to put it:",
    "Said differently —",
    "Same read, tighter:",
    "Put simply:",
    "The short version:",
    "From the other side:",
)


def _rewrite_opening(reply: str, style: str) -> str:
    body = reply.strip()
    if not body:
        return body
    lead = _ALT_LEADS[_style_idx(style) % len(_ALT_LEADS)]
    first_line, sep, rest = body.partition(". ")
    if sep and len(first_line) < 140:
        return f"{lead} {first_line[0].lower()}{first_line[1:]}{sep}{rest}"
    return f"{lead} {body}"


def _close_pair_note(item: ClaraAction) -> str:
    if item.reason and item.reason.startswith("close_pair"):
        return item.reason.split(":", 1)[-1].strip()
    return ""


def _pending_rerun_reply(context: dict[str, Any], item: ClaraAction, style: str) -> str:
    gene = _focused_gene(context) or "the focused gene"
    disease = item.disease or _disease(context) or "this disease"
    gene_s = ", ".join(item.genes) or gene
    current = _session_genes(context)
    dropped = [g for g in current if g not in (item.genes or [])]
    drop = f" Dropping {', '.join(dropped)} — this run is only {gene_s}." if dropped else ""
    note = _close_pair_note(item)
    if note:
        return _pick_line(
            style,
            [
                f"{gene_s} is the {note}. I'll run {disease} × {gene_s} on Live.{drop} Confirm when you want that pair.",
                f"{gene_s} sits on the same axis ({note}).{drop} Confirm and I'll Live-retrieve real papers.",
                f"{gene_s} is the closest neighbour ({note}), with the usual caveat that a neighbour hit can be pathway-shared.{drop} Confirm to run it alone on Live.",
                f"The next pair to test is {disease} × {gene_s} ({note}).{drop} Confirm and I'll switch to Live.",
                f"{gene_s} is a {note} and already has a packed dossier.{drop} Confirm to Live-run that gene only.",
                f"If the {gene} signal is shared, {gene_s} ({note}) should light up too.{drop} Confirm and I'll run {gene_s} alone on Live.",
            ],
        )
    return _pick_line(
        style,
        [
            f"This run becomes {disease} × {gene_s}.{drop} Confirm and I'll switch to Live.",
            f"{disease} × {gene_s} only — that's the next retrieve.{drop} Confirm and I'll go Live.",
            f"Narrowing to {gene_s} on {disease}.{drop} Confirm when you want Live papers.",
        ],
    )


def _offline_reply(
    context: dict[str, Any],
    pending: list[ClaraAction],
    actions: list[ClaraAction],
    activity: list[str],
    style: str,
    *,
    last_user: str = "",
    degraded: bool = False,
) -> str:
    gene = _focused_gene(context) or "the focused gene"
    disease = _disease(context) or "this disease"

    if pending:
        item = pending[0]
        if item.type == "rerun":
            return _pending_rerun_reply(context, item, style)
        if item.type == "search":
            target = item.gene or gene
            dx = item.disease or disease
            return _pick_line(
                style,
                [
                    f"I'll search Europe PMC for {target} × {dx}, skipping papers already in the dossier. Confirm to run it.",
                    f"Literature only — {target} × {dx} on Europe PMC, filtered against your current cards. Confirm when you want the search.",
                    f"A Europe PMC pass for {target} on {dx}, no re-score. Confirm to fetch it.",
                ],
            )
        if item.type == "focus_gene":
            return f"I'll switch the workbench to {item.gene}. Confirm when you want that focus."
        return f"{item.label} — Confirm when you want it."

    executed = actions[0] if actions else None
    if executed and executed.type == "rerun":
        gene_s = ", ".join(executed.genes) or executed.gene or gene
        dx = executed.disease or disease
        return _pick_line(
            style,
            [
                f"On it. Watch the workbench — I'll switch to Live, set {dx} × {gene_s} only, and click Run analysis.",
                f"Confirmed. Watch the workbench: Live, {dx} × {gene_s}, then Run analysis.",
                f"Watch the workbench — Live mode, {dx} × {gene_s} only, then Run.",
            ],
        )
    if executed and executed.type == "search":
        if executed.hits:
            titles = "; ".join(hit.title for hit in executed.hits[:2])
            return (
                f"Europe PMC returned {len(executed.hits)} paper(s) not already in your dossier — "
                f"most notable: {titles}. Sources are attached under this message."
            )
        return (
            f"Europe PMC didn't surface newer papers beyond your dossier for "
            f"{executed.gene or gene} × {executed.disease or disease}. Want me to widen the query?"
        )

    if _is_verdict_pushback(last_user):
        return _explain_verdict(context, style, last_user)
    if _is_citation_ask(last_user):
        return _citation_reply(context, style)
    if last_user.strip():
        return _acknowledge_ask(context, style, last_user, degraded=degraded)

    line = _pick_line(
        style,
        [
            f"Tell me what feels off about the {gene} verdict and I'll dig in.",
            f"The anchor for {gene} on {disease} is the pathway-to-clinical link. Where do you want to press?",
            f"I can pull citations, queue a close-pair rerun, or challenge the {gene} call — your move.",
        ],
    )
    if degraded:
        line += " (From the dossier only — the LLM link is flaky.)"
    return line


async def chat_completion(
    request: ChatRequest,
    *,
    user_id: str | None = None,
    user_email: str | None = None,
) -> ChatResponse:
    context = _verified_context(
        request.context,
        user_id=user_id,
        user_email=user_email,
    )
    last_user = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
    actions: list[ClaraAction] = []
    pending: list[ClaraAction] = []
    activity: list[str] = []
    extra = ""

    to_run = list(request.confirm)
    if not to_run:
        for command in parse_commands(last_user, context):
            action = _action_from_command(command, context)
            if action.type in _NEEDS_CONFIRM:
                pending.append(action)
            elif action.type == "defend":
                extra += "\nUSER WANTS YOU TO DEFEND the focused verdict using the dossier. Steelman it. Do not change the official verdict.\n"
            elif action.type == "argue":
                extra += "\nUSER WANTS YOU TO CHALLENGE the focused verdict using the dossier. Argue the opposite case. Do not change the official verdict.\n"
            elif action.type == "compare":
                extra += "\nUSER ASKED TO COMPARE all session candidates.\n"
    else:
        extra += "The scientist CONFIRMED the pending action. It is running now.\n"

    for action in to_run:
        kind = action.type
        if kind == "search":
            gene = action.gene or _focused_gene(context)
            disease = action.disease or _disease(context)
            activity.append(f"Searching Europe PMC for newer papers on {gene} × {disease}")
            query, hits = await _search_europe_pmc(gene, disease)
            hits = _filter_novel_hits(hits, context)
            executed = action.model_copy(update={"query": query, "hits": hits, "gene": gene, "disease": disease})
            actions.append(executed)
            if hits:
                extra += (
                    "LIVE SEARCH RESULTS (additional papers NOT already in the dossier; "
                    "mention each by title and citation only — do not paste URLs):\n"
                    + "\n".join(f"  - {h.title} ({h.citation})" for h in hits)
                )
            else:
                extra += (
                    "LIVE SEARCH RESULTS: no additional papers beyond what is already in the dossier "
                    f"for {query}. Say that plainly in your reply.\n"
                )
        elif kind == "focus_gene":
            activity.append(f"Switching workbench to {action.gene}")
            actions.append(action)
        elif kind == "rerun":
            next_disease = action.disease or _disease(context)
            next_genes = [g for g in (action.genes or []) if g] or _session_genes(context)
            current_disease = _disease(context)
            current_genes = ", ".join(_session_genes(context))
            gene_s = ", ".join(next_genes)
            if next_disease != current_disease:
                activity.append(f"Disease: {current_disease} → {next_disease}")
            else:
                activity.append(f"Disease: {next_disease}")
            if gene_s != current_genes:
                activity.append(f"Genes: {current_genes} → {gene_s}")
            else:
                activity.append(f"Genes: {gene_s}")
            current_mode = str(context.get("mode") or "demo").strip().lower()
            if current_mode != "live":
                activity.append("Mode: Demo → Live")
            else:
                activity.append("Mode: Live")
            activity.append("Agents: retrieve → extract → score → falsify → decide")
            actions.append(action.model_copy(update={"disease": next_disease, "genes": next_genes}))

    if pending:
        extra += "PENDING ACTIONS (not run until Confirm is tapped under this message):\n"
        for item in pending:
            extra += f"  - {item.label}\n"
            if item.type == "rerun":
                extra += f"    Disease will become: {item.disease}\n"
                extra += f"    Genes will become: {', '.join(item.genes) or '(unchanged)'}\n"
                extra += "    Mode will switch to Live so Retrieve hits Open Targets + Europe PMC, not the seeded Demo fixture.\n"
                extra += "    This gene list REPLACES the current session. Do not say other candidates will also run.\n"
                if item.reason and item.reason.startswith("close_pair"):
                    note = item.reason.split(":", 1)[1] if ":" in item.reason else "close pair"
                    extra += f"    Why this pair: {note}. Name the pathway link out loud.\n"

    provider = OpenAICompatibleProvider()
    search_hits = next((item.hits for item in actions if item.type == "search"), [])
    style = _pick_style(request, last_user)
    prior_assistant = [m.content for m in request.messages if m.role == "assistant" and m.content][-3:]
    if prior_assistant:
        extra += "\nPRIOR ASSISTANT REPLIES (do not repeat their opening or phrasing):\n"
        for text in prior_assistant:
            extra += f"  - {text[:220].strip()}\n"

    confirming_rerun = any(item.type == "rerun" for item in to_run)
    skip_llm = bool(
        pending
        or confirming_rerun
        or _is_verdict_pushback(last_user)
        or _is_citation_ask(last_user)
    )

    def grounded(degraded: bool = False) -> str:
        return _strip_vocative(
            _offline_reply(
                context,
                pending,
                actions,
                activity,
                style,
                last_user=last_user,
                degraded=degraded,
            )
        )

    if skip_llm:
        return await _remember(
            request,
            ChatResponse(
                reply=grounded(),
                grounded=True,
                actions=actions,
                pending=pending,
                activity=activity,
            ),
            context=context,
            user_id=user_id,
            user_email=user_email,
        )

    if not provider.enabled:
        return await _remember(
            request,
            ChatResponse(
                reply=_ensure_hits_in_reply(grounded(), search_hits),
                grounded=True,
                actions=actions,
                pending=pending,
                activity=activity,
            ),
            context=context,
            user_id=user_id,
            user_email=user_email,
        )

    first_name = "(do not address by name — never open a reply with a name)"
    system_content = (
        SYSTEM_PROMPT.replace("{context}", _format_context(context, extra))
        .replace("{style}", style)
        .replace("{first_name}", first_name)
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
    for msg in request.messages[-12:]:
        if msg.role not in {"user", "assistant"}:
            continue
        content = _strip_vocative(msg.content) if msg.role == "assistant" else msg.content
        messages.append({"role": msg.role, "content": content})

    try:
        reply = await provider.chat(messages)
        reply = _strip_vocative(reply)
        if not reply or _reply_is_unsafe(reply, last_user):
            reply = grounded()
        elif _too_similar(reply, prior_assistant):
            reply = _rewrite_opening(reply, style)
            if _reply_is_unsafe(reply, last_user):
                reply = grounded()
        reply = _ensure_hits_in_reply(reply, search_hits)
        return await _remember(
            request,
            ChatResponse(
                reply=_strip_vocative(reply),
                grounded=True,
                actions=actions,
                pending=pending,
                activity=activity,
            ),
            context=context,
            user_id=user_id,
            user_email=user_email,
        )
    except Exception:
        return await _remember(
            request,
            ChatResponse(
                reply=_ensure_hits_in_reply(grounded(True), search_hits),
                grounded=False,
                actions=actions,
                pending=pending,
                activity=activity,
            ),
            context=context,
            user_id=user_id,
            user_email=user_email,
        )
