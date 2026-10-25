from tests.fixtures import job_payload


def test_health_reports_mongodb_ok(client):
    body = client.get("/health").json()
    assert body["mongodb"] == "ok"
    assert body["dry_run"] is True


def test_import_list_and_get_job(client):
    created = client.post("/api/jobs/import", json=job_payload("int-1")).json()
    assert created["source_job_id"] == "int-1"
    assert 0 <= created["match_score"] <= 100

    listed = client.get("/api/jobs").json()
    assert [job["id"] for job in listed] == [created["id"]]

    detail = client.get(f"/api/jobs/{created['id']}").json()
    assert set(detail["match_factors"]) == {"skills", "role", "experience", "domain", "location"}


def test_reimporting_same_job_returns_existing_record(client):
    first = client.post("/api/jobs/import", json=job_payload("int-dup")).json()
    second = client.post("/api/jobs/import", json=job_payload("int-dup")).json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/jobs").json()) == 1


def test_unknown_job_returns_404(client):
    assert client.get("/api/jobs/not-an-id").status_code == 404
    assert client.get("/api/jobs/0123456789abcdef01234567").status_code == 404


def test_application_is_dry_run_and_not_duplicated(client):
    job = client.post("/api/jobs/import", json=job_payload("int-app")).json()

    app_record = client.post("/api/applications", json={"job_id": job["id"]}).json()
    assert app_record["dry_run"] is True
    assert app_record["status"] == "dry_run"

    again = client.post("/api/applications", json={"job_id": job["id"]}).json()
    assert again["duplicate"] is True
    assert again["id"] == app_record["id"]
    assert len(client.get("/api/applications").json()) == 1


def test_low_score_job_cannot_be_prepared(client):
    payload = job_payload("int-low", title="Gardener", description="Seasonal gardening and landscape design")
    job = client.post("/api/jobs/import", json=payload).json()
    response = client.post("/api/applications", json={"job_id": job["id"]})
    assert response.status_code == 422


def test_live_mode_cannot_be_enabled(client):
    response = client.put("/api/settings", json={"dry_run": False, "minimum_match_score": 50})
    assert response.status_code == 400
    assert client.get("/api/settings").json()["dry_run"] is True
