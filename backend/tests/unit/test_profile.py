from app.core.config import settings
from app.scoring.engine import score_job
from app.scoring.profile import load_profile, profile_status


def test_missing_profile_is_reported_and_no_file_is_created(tmp_path, monkeypatch):
    path = tmp_path / "profile.json"
    monkeypatch.setattr(settings, "profile_path", str(path))
    profile, text, notes = load_profile()
    status = profile_status()
    assert profile is None
    assert text is None
    assert notes == ["profile_missing"]
    assert status["profile_present"] is False
    assert status["warnings"] == ["profile_missing"]
    assert "No profile file" in status["message"]
    assert "name" not in status
    assert path.exists() is False


def test_pdf_resume_is_read_without_changing_the_file(tmp_path, monkeypatch):
    resumes = tmp_path / "resumes"
    resumes.mkdir()
    resume = resumes / "original.pdf"
    resume.write_bytes(_pdf("Built services with Python."))
    original = resume.read_bytes()
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        '{"preferred_roles":["Backend Engineer"],"resume_filename":"original.pdf"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "profile_path", str(profile_path))
    monkeypatch.setattr(settings, "resume_storage_path", str(resumes))

    profile, text, notes = load_profile()
    assert notes == []
    assert text is not None
    assert "Python" in text
    assert resume.read_bytes() == original
    result = score_job(
        {"title": "Backend Engineer", "description": "Requirements: Python."},
        profile,
        threshold=50,
        resume_text=text,
    )
    assert result.matched_skills == ["python"]
    status = profile_status()
    assert status["resume_text_available"] is True
    assert "original.pdf" not in status["message"]


def test_unreadable_resume_does_not_invent_skills(tmp_path, monkeypatch):
    resumes = tmp_path / "resumes"
    resumes.mkdir()
    (resumes / "notes.docx").write_bytes(b"not a resume")
    profile_path = tmp_path / "profile.json"
    profile_path.write_text('{"preferred_roles":["Backend Engineer"],"resume_filename":"notes.docx"}', encoding="utf-8")
    monkeypatch.setattr(settings, "profile_path", str(profile_path))
    monkeypatch.setattr(settings, "resume_storage_path", str(resumes))
    profile, text, notes = load_profile()
    assert text is None
    assert notes == ["resume_text_unavailable"]
    result = score_job(
        {"title": "Backend Engineer", "description": "Requirements: Python."},
        profile,
        threshold=50,
        resume_text=text,
    )
    assert result.matched_skills == []
    assert result.missing_skills == ["python"]


def _pdf(sentence: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({sentence}) Tj ET\n".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body.extend(f"{number} 0 obj\n".encode("ascii"))
        body.extend(obj)
        body.extend(b"\nendobj\n")
    xref = len(body)
    body.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    body.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(body)
