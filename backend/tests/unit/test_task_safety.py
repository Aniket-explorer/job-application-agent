from app.tasks import hourly_scan

def test_hourly_scan_does_not_call_sources():
    result = hourly_scan.run()
    assert result["status"] == "dry_run"
    assert result["dry_run"] is True
    assert "no external requests" in result["message"]
