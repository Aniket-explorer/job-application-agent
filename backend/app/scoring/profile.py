import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from app.core.config import settings
from app.core.errors import AppError
from app.scoring.engine import ProfileFacts


class ProfileInvalidError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("profile_invalid", 422, message)


def profile_status(path: Path | None = None) -> dict:
    """Report whether the configured profile and resume can be read. Returns no personal fields."""
    try:
        profile, resume_text, notes = load_profile(path)
    except ProfileInvalidError as exc:
        return _status(True, False, False, ["profile_invalid"], str(exc))
    if profile is None:
        return _status(
            False,
            False,
            False,
            ["profile_missing"],
            "No profile file was found. Add storage/profile.json with only facts you can confirm. No skills or qualifications are assumed until that file exists.",
        )
    if "resume_not_configured" in notes:
        message = "The profile does not name a resume in storage/resumes, or that file is missing. Scoring uses only the facts in the profile. The resume file is never modified."
    elif "resume_text_unavailable" in notes:
        message = "The resume file could not be read as text. The original file was not modified, and no skills were inferred from it."
    elif resume_text is None:
        message = "Resume text is not available. No skills were inferred."
    else:
        message = "The profile and resume text are available. Scoring uses only stated skills and qualifications."
    return _status(True, True, resume_text is not None, notes, message)


def _status(present: bool, valid: bool, resume_ready: bool, warnings: list[str], message: str) -> dict:
    return {
        "profile_present": present,
        "profile_valid": valid,
        "resume_text_available": resume_ready,
        "warnings": warnings,
        "message": message,
    }


def load_profile(path: Path | None = None) -> tuple[ProfileFacts | None, str | None, list[str]]:
    """Read the local profile and, when named, the original resume. Never writes either file."""
    profile_path = path or Path(settings.profile_path)
    if not profile_path.is_file():
        return None, None, ["profile_missing"]
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ProfileInvalidError("The profile file is not valid JSON.") from None
    if not isinstance(payload, dict):
        raise ProfileInvalidError("The profile file must contain an object.")
    for private in ("name", "email", "phone"):
        payload.pop(private, None)
    try:
        profile = ProfileFacts.model_validate(payload)
    except ValidationError:
        raise ProfileInvalidError("The profile file is missing a usable field.") from None
    resume_text, notes = _read_resume(profile.resume_filename)
    return profile, resume_text, notes


def profile_fingerprint(profile: ProfileFacts | None, resume_text: str | None) -> str:
    body = {
        "profile": profile.model_dump() if profile else None,
        "resume_sha256": hashlib.sha256((resume_text or "").encode("utf-8")).hexdigest(),
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _read_resume(filename: str | None) -> tuple[str | None, list[str]]:
    if not filename:
        return None, ["resume_not_configured"]
    if "/" in filename or "\\" in filename or filename.startswith("."):
        return None, ["resume_not_configured"]
    suffix = Path(filename).suffix.lower()
    if suffix not in {".txt", ".md", ".pdf"}:
        return None, ["resume_text_unavailable"]
    root = Path(settings.resume_storage_path).resolve()
    candidate = (root / filename).resolve()
    if root != candidate.parent:
        return None, ["resume_not_configured"]
    if not candidate.is_file():
        return None, ["resume_not_configured"]
    if suffix == ".pdf":
        return _read_pdf(candidate)
    try:
        return candidate.read_text(encoding="utf-8"), []
    except (OSError, UnicodeError):
        return None, ["resume_text_unavailable"]


def _read_pdf(path: Path) -> tuple[str | None, list[str]]:
    """Extract text in memory. pypdf does not write the original PDF."""
    before = path.read_bytes()
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:
        return None, ["resume_text_unavailable"]
    if path.read_bytes() != before:
        return None, ["resume_text_unavailable"]
    if not text:
        return None, ["resume_text_unavailable"]
    return text, []
