from contextlib import asynccontextmanager
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import DuplicateKeyError
from app.config import settings
from app.db import get_db, ensure_indexes, close_db
from app.models import JobImport, ApplicationCreate, AutomationSettings
from app.matching import calculate_match_score
from app.connectors.stubs import CONNECTORS

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await ensure_indexes()
    except Exception as exc:
        # Startup should still expose health/docs when Mongo is temporarily unavailable.
        app.state.db_startup_error = str(exc)
    yield
    await close_db()

app = FastAPI(title="AI Job Application Agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False, allow_methods=["GET", "POST", "PUT", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])
_settings = AutomationSettings(dry_run=True, minimum_match_score=settings.min_match_score)

def serialize_job(doc: dict) -> dict:
    return {"id": str(doc["_id"]), "source": doc["source"], "source_job_id": doc["source_job_id"], "company": doc["company"], "title": doc["title"], "location": doc.get("location"), "description": doc["description"], "canonical_url": doc["canonical_url"], "match_score": doc.get("match_score"), "status": doc.get("status", "active"), "created_at": doc["created_at"]}

def serialize_application(doc: dict) -> dict:
    return {"id": str(doc["_id"]), "job_id": doc["job_id"], "candidate_id": doc["candidate_id"], "channel": doc["channel"], "status": doc["status"], "match_score": doc["match_score"], "dry_run": doc["dry_run"], "created_at": doc["created_at"], "error": doc.get("error")}

@app.get("/health")
async def health():
    try:
        await get_db().command("ping")
        mongo = "ok"
    except Exception:
        mongo = "unavailable"
    return {"status": "ok" if mongo == "ok" else "degraded", "mongodb": mongo, "dry_run": True}

@app.get("/api/connectors")
async def connector_statuses():
    return [c.capabilities().__dict__ for c in CONNECTORS.values()]

@app.post("/api/jobs/import")
async def import_job(payload: JobImport):
    db = get_db()
    now = datetime.now(timezone.utc)
    score = calculate_match_score(payload.description)
    doc = payload.model_dump(mode="json")
    doc.update({"canonical_url": str(payload.canonical_url), "match_score": score["score"], "match_factors": score["factors"], "match_reasons": score["reasons"], "status": "active", "created_at": now, "updated_at": now})
    try:
        result = await db.jobs.insert_one(doc)
        doc["_id"] = result.inserted_id
    except DuplicateKeyError:
        existing = await db.jobs.find_one({"source": payload.source, "source_job_id": payload.source_job_id})
        if not existing:
            raise HTTPException(status_code=409, detail="Duplicate job detected")
        doc = existing
    return serialize_job(doc)

@app.get("/api/jobs")
async def list_jobs(limit: int = 50, min_score: int = 0):
    limit = max(1, min(limit, 200))
    cursor = get_db().jobs.find({"match_score": {"$gte": min_score}}).sort("created_at", -1).limit(limit)
    return [serialize_job(doc) async for doc in cursor]

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    doc = await get_db().jobs.find_one({"_id": ObjectId(job_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    result = serialize_job(doc)
    result["match_factors"] = doc.get("match_factors", {})
    result["match_reasons"] = doc.get("match_reasons", [])
    return result

@app.post("/api/applications")
async def create_application(payload: ApplicationCreate):
    db = get_db()
    if not ObjectId.is_valid(payload.job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    job = await db.jobs.find_one({"_id": ObjectId(payload.job_id)})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    score = float(job.get("match_score", 0))
    if score < _settings.minimum_match_score:
        raise HTTPException(status_code=422, detail=f"Match score {score} is below threshold {_settings.minimum_match_score}")
    now = datetime.now(timezone.utc)
    doc = {"job_id": payload.job_id, "candidate_id": payload.candidate_id, "channel": job["source"], "status": "dry_run", "match_score": score, "dry_run": True, "created_at": now, "updated_at": now, "submitted_at": None, "error": None}
    try:
        result = await db.applications.insert_one(doc)
        doc["_id"] = result.inserted_id
    except DuplicateKeyError:
        existing = await db.applications.find_one({"job_id": payload.job_id, "candidate_id": payload.candidate_id})
        return {**serialize_application(existing), "duplicate": True}
    await db.audit_events.insert_one({"entity_id": str(doc["_id"]), "event": "application_dry_run_created", "details": {"job_id": payload.job_id, "score": score}, "created_at": now})
    return serialize_application(doc)

@app.get("/api/applications")
async def list_applications(limit: int = 100):
    limit = max(1, min(limit, 200))
    cursor = get_db().applications.find().sort("created_at", -1).limit(limit)
    return [serialize_application(doc) async for doc in cursor]

@app.get("/api/settings")
async def get_settings():
    return _settings.model_dump()

@app.put("/api/settings")
async def update_settings(payload: AutomationSettings):
    # Live mode is intentionally impossible in this scaffold.
    if payload.dry_run is not True:
        raise HTTPException(status_code=400, detail="Live mode is not implemented. Keep dry_run=true until provider-specific controls and tests exist.")
    global _settings
    _settings = payload
    return _settings.model_dump()
