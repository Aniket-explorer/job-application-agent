def serialize_job(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "source": doc["source"],
        "source_job_id": doc["source_job_id"],
        "company": doc["company"],
        "title": doc["title"],
        "location": doc.get("location"),
        "description": doc["description"],
        "canonical_url": doc["canonical_url"],
        "match_score": doc.get("match_score"),
        "status": doc.get("status", "active"),
        "created_at": doc["created_at"],
    }


def serialize_job_detail(doc: dict) -> dict:
    result = serialize_job(doc)
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
