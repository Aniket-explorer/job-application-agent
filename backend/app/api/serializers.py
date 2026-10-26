from app.connectors.career_page.greenhouse import public_source_job_id, split_legacy_greenhouse_source_job_id, url_embeds_board_token


def _public_job_fields(doc: dict) -> tuple[str, object]:
    """Hide a legacy board slug in the id and URL without inventing a replacement link."""
    source_job_id = str(doc.get("source_job_id", ""))
    canonical_url = doc.get("canonical_url")
    parsed = split_legacy_greenhouse_source_job_id(source_job_id)
    if parsed is not None:
        token, _job_id = parsed
        source_job_id = public_source_job_id(source_job_id)
        if isinstance(canonical_url, str) and url_embeds_board_token(canonical_url, token):
            canonical_url = None
    return source_job_id, canonical_url


def job_origin(doc: dict) -> str:
    origin = doc.get("origin")
    if origin in {"manual", "discovered"}:
        return origin
    if doc.get("source") == "manual":
        return "manual"
    return "discovered"


def serialize_job(doc: dict, assessment: dict | None = None) -> dict:
    source_job_id, canonical_url = _public_job_fields(doc)
    body = {
        "id": str(doc["_id"]),
        "source": doc["source"],
        "source_job_id": source_job_id,
        "company": doc["company"],
        "title": doc["title"],
        "location": doc.get("location"),
        "description": doc.get("description"),
        "canonical_url": canonical_url,
        "match_score": doc.get("match_score"),
        "origin": job_origin(doc),
        "status": doc.get("status", "active"),
        "created_at": doc["created_at"],
    }
    if assessment is not None:
        body["assessment"] = assessment
    return body


def serialize_job_detail(doc: dict, assessment: dict | None = None) -> dict:
    result = serialize_job(doc, assessment)
    result["match_factors"] = doc.get("match_factors", {})
    result["match_reasons"] = doc.get("match_reasons", [])
    return result


def serialize_application(doc: dict, *, duplicate: bool = False) -> dict:
    body = {
        "id": str(doc["_id"]),
        "job_id": doc["job_id"],
        "candidate_id": doc["candidate_id"],
        "channel": doc["channel"],
        "status": doc["status"],
        "match_score": doc["match_score"],
        "dry_run": doc.get("dry_run", True),
        "created_at": doc["created_at"],
        "error": doc.get("error"),
    }
    if duplicate:
        body["duplicate"] = True
    return body


def page(items: list, *, total: int, page_number: int, page_size: int) -> dict:
    return {"items": items, "total": total, "page": page_number, "page_size": page_size}
