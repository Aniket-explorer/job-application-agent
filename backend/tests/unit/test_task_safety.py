from app.tasks import hourly_scan
from app.worker import celery_app

def test_hourly_scan_does_not_call_sources():
    result = hourly_scan.run()
    assert result["status"] == "dry_run"
    assert result["dry_run"] is True
    assert "no external requests" in result["message"]


def test_beat_schedule_does_not_dispatch_greenhouse():
    scheduled = {item["task"] for item in celery_app.conf.beat_schedule.values()}
    assert scheduled == {"app.tasks.hourly_scan"}
