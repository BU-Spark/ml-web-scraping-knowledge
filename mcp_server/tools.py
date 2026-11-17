"""Nine evidence-first MCP tools. Analysis helpers never call an LLM.

Source content is data, never executable instructions. Comparative/audit results
are review material, not assertions of causal effectiveness or business scores.
"""
import re
from typing import Any

from mcp_server.filters import required_text, result_limit, tokens
from mcp_server.retrieval import RetrievalService

service = RetrievalService()


def get_sales_methodology(query: str, entity: str | None = None, topic: str | None = None,
                          role: str | None = None, industry: str | None = None,
                          company_size: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Retrieve cited sales methodology/process guidance. Entity supports MEDDIC/MEDDICC aliases.

    Optional filters are literal metadata matches; company_size filters context.company_size,
    role filters context.who. Missing metadata will not match an active filter.
    """
    return service.search(query, category="Sales Methodology and Process", entity=entity,
                          topic=topic, role=role, industry=industry, company_size=company_size, limit=limit)


def get_segmentation_guidance(query: str, entity: str | None = None, topic: str | None = None,
                              role: str | None = None, industry: str | None = None,
                              company_size: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Retrieve cited segmentation, territory, ICP, or account-tier guidance.

    Use company_size for source-supported SMB/commercial/enterprise context; do not
    assume those segment definitions are universal across publishers.
    """
    return service.search(query, category="Segmentation and Territory", entity=entity,
                          topic=topic, role=role, industry=industry, company_size=company_size, limit=limit)


def get_enablement_practices(query: str, entity: str | None = None, topic: str | None = None,
                             role: str | None = None, industry: str | None = None,
                             company_size: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Retrieve cited enablement, onboarding, coaching, training, and operations practices."""
    return service.search(query, category="Enablement Operations", entity=entity,
                          topic=topic, role=role, industry=industry, company_size=company_size, limit=limit)


def get_source(identifier: str, identifier_type: str = "unit_id", limit: int = 5) -> dict[str, Any]:
    """Look up stored evidence and its exact parent chunk by unit_id, chunk_id, doc_id, or url.

    Does not fetch live URLs. Returns only sources with served knowledge units, respects
    deployment visibility policy, and requires no query embedding. Results may be limited.
    """
    return service.source(identifier, identifier_type, limit)


def get_objection_handling(objection: str, entity: str | None = None,
                           company_size: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Find source-supported objection-handling guidance across categories.

    Returns candidate practices and evidence, not a fabricated rebuttal or a guarantee
    that the practice answers the objection. Inspect citations before using advice.
    """
    objection = required_text(objection, "objection", 6000)
    return service.search("Objection handling: " + objection, entity=entity,
                          company_size=company_size, limit=limit)


def compare_approaches(approaches: list[str], question: str, limit_per_approach: int = 3) -> dict[str, Any]:
    """Retrieve separate cited evidence for 2..4 named approaches (e.g. MEDDICC and BANT).

    Each name is a literal entity filter; unsupported approaches stay empty. Does not
    rank winners or claim two sources were evaluated in comparable conditions.
    """
    question = required_text(question, "question", 6000)
    result_limit(limit_per_approach)
    if not isinstance(approaches, list) or not 2 <= len(approaches) <= 4:
        raise ValueError("Provide 2..4 distinct approaches")
    names = [required_text(name, "approach", 200) for name in approaches]
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Approaches must be distinct")
    comparisons = [{"approach": name, **service.search(
        name + ": " + question, entity=name, limit=limit_per_approach)} for name in names]
    count = sum(bool(item["results"]) for item in comparisons)
    return {"status": "ok" if count == len(names) else "insufficient_evidence",
            "comparisons": comparisons,
            "message": "Compare cited claims, contexts and outcomes; missing evidence is not evidence of inferiority. No winner is inferred."}


def map_value_drivers(customer_context: str, offering: str, limit: int = 5) -> dict[str, Any]:
    """Retrieve candidate value-driver evidence for a customer context and offering.

    Returns the source's claim/context and reported outcome for each candidate. It does
    not assert customer applicability, invent ROI, or map unsupported product capabilities.
    """
    customer_context = required_text(customer_context, "customer_context", 4000)
    offering = required_text(offering, "offering", 4000)
    response = service.search(f"Value drivers and business outcomes for {offering}. Customer context: {customer_context}", limit=limit)
    response["candidate_value_drivers"] = [{"candidate": item["claim"],
        "source_context": item["context"], "reported_outcome": item["outcome"],
        "citation": item["citation"], "applicability": "requires_review"} for item in response["results"]]
    response["message"] += " Candidate drivers require human review against actual customer needs and product capabilities."
    return response


def audit_messaging_alignment(message: str, reference_query: str, limit: int = 5) -> dict[str, Any]:
    """Retrieve cited reference guidance and flag shared words for messaging review.

    This is an evidence-assisted lexical review, not semantic entailment, contradiction
    detection, or a compliance verdict. An overlap does not prove alignment.
    """
    message = required_text(message, "message", 6000)
    reference_query = required_text(reference_query, "reference_query", 4000)
    response = service.search(reference_query, limit=limit)
    stop = {"a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "is", "are", "with", "be", "by", "as"}
    message_terms = tokens(message) - stop
    response["review_items"] = [{"unit_id": item["unit_id"],
        "shared_terms": sorted(message_terms & (tokens(item["claim"]) - stop)),
        "assessment": "requires_review", "citation": item["citation"]} for item in response["results"]]
    response["method"] = "case-insensitive word overlap; no semantic alignment verdict"
    response["message"] = ("Review each cited practice against the message; shared words do not establish adherence."
                           if response["results"] else response["message"])
    return response


def score_adherence_metric(content: str, criteria: list[str]) -> dict[str, Any]:
    """Score explicit phrase coverage of a caller-supplied checklist, from 0 to 100.

    Each criterion is a literal phrase to find, equally weighted. Matching ignores case
    and collapses whitespace, but requires word boundaries. Negation/meaning are not
    interpreted. This is NOT a validated sales-quality, semantic, or compliance metric.
    Requires no database; returns excerpts so every positive match is auditable.
    """
    content = required_text(content, "content", 12000)
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 20:
        raise ValueError("Provide 1..20 explicit phrase criteria")
    phrases = [required_text(phrase, "criterion", 200) for phrase in criteria]
    keys = [" ".join(phrase.casefold().split()) for phrase in phrases]
    if len(set(keys)) != len(keys):
        raise ValueError("Criteria must be distinct")
    findings = []
    for phrase in phrases:
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(word) for word in phrase.split()) + r"(?!\w)"
        match = re.search(pattern, content, re.IGNORECASE)
        findings.append({"criterion": phrase, "matched": bool(match),
                         "evidence": content[match.start():match.end()] if match else None,
                         "start": match.start() if match else None, "end": match.end() if match else None})
    matched = sum(item["matched"] for item in findings)
    return {"status": "ok", "metric": "explicit_phrase_coverage", "score": round(100 * matched / len(findings), 2),
            "matched": matched, "total": len(findings), "criteria": findings,
            "formula": "100 * matched phrases / supplied phrases (equal weights)",
            "limitations": "Literal text matching only; negated statements can match. Not a semantic adherence or effectiveness score."}


TOOL_FUNCTIONS = (get_sales_methodology, get_segmentation_guidance, get_enablement_practices,
                  get_source, get_objection_handling, compare_approaches, map_value_drivers,
                  audit_messaging_alignment, score_adherence_metric)
