import filters
import main
import pipeline
import store


def make_jobs(count):
    jobs = []
    for number in range(count):
        jobs.append({
            "job_id": f"job-{number}", "company": f"Company {number}", "title": "Engineer",
            "location": "London", "url": "https://example.com", "description": "text", "source": "test",
        })
    return jobs


def set_up(monkeypatch, tmp_path, jobs, scores):
    """Replaces everything that would call the internet or Claude."""
    monkeypatch.setattr(store, "RESULTS_FILE", str(tmp_path / "results.json"))
    score_iterator = iter(scores)

    def fake_profile():
        return "facts", "voice"

    def fake_find_new_jobs():
        return jobs, {}

    def fake_save_letter(job, letter):
        return "path"

    def fake_save_seen(path, seen):
        return None

    monkeypatch.setattr(main, "load_profile", fake_profile)
    monkeypatch.setattr(main, "find_new_jobs", fake_find_new_jobs)
    monkeypatch.setattr(main, "save_letter", fake_save_letter)
    monkeypatch.setattr(filters, "save_seen_jobs", fake_save_seen)

    def fake_score(fact_bank, job):
        return next(score_iterator)

    def fake_letter(fact_bank, voice, job, score_result):
        return "A letter", True, "Passed first check"

    monkeypatch.setattr(main, "score_job", fake_score)
    monkeypatch.setattr(main, "write_letter", fake_letter)


def good(score):
    return {"score": score, "verdict": "apply", "reasons": ["r"], "red_flags": [], "hard_blockers": []}


def test_run_saves_scored_jobs_and_writes_letters_only_above_threshold(monkeypatch, tmp_path):
    set_up(monkeypatch, tmp_path, make_jobs(2), [good(80), good(40)])
    counts = pipeline.run_pipeline(10, False)
    assert counts["scored"] == 2
    assert counts["letters"] == 1
    results = store.load_results()
    assert results["job-0"]["status"] == store.STATUS_READY
    assert results["job-0"]["letter"] == "A letter"
    assert results["job-1"]["status"] == store.STATUS_SCORED_ONLY


def test_failed_scoring_is_not_saved(monkeypatch, tmp_path):
    failed = {"score": 0, "verdict": "skip", "failed": True}
    set_up(monkeypatch, tmp_path, make_jobs(2), [failed, good(70)])
    counts = pipeline.run_pipeline(10, False)
    assert counts["failed"] == 1
    assert counts["scored"] == 1
    assert "job-0" not in store.load_results()


def test_limit_caps_how_many_are_scored(monkeypatch, tmp_path):
    set_up(monkeypatch, tmp_path, make_jobs(5), [good(50), good(50), good(50)])
    counts = pipeline.run_pipeline(3, False)
    assert counts["scored"] == 3


def test_mark_applied_without_sheet(monkeypatch, tmp_path):
    set_up(monkeypatch, tmp_path, make_jobs(1), [good(50)])
    pipeline.run_pipeline(10, False)
    message = pipeline.mark_applied("job-0", False)
    assert message == "Marked as applied."
    record = store.load_results()["job-0"]
    assert record["status"] == store.STATUS_APPLIED
    assert record["date_applied"] != ""
    assert pipeline.mark_applied("job-0", False) == "Already marked as applied."


def test_write_letter_for_record(monkeypatch, tmp_path):
    set_up(monkeypatch, tmp_path, make_jobs(1), [good(50)])
    pipeline.run_pipeline(10, False)
    record = pipeline.write_letter_for_record("job-0")
    assert record["letter"] == "A letter"
    assert record["status"] == store.STATUS_READY


def test_pasted_advert_is_saved_to_queue(monkeypatch, tmp_path):
    set_up(monkeypatch, tmp_path, [], [good(75)])
    record = pipeline.score_pasted_advert("Acme", "Analyst", "", "Advert", True)
    assert record["job_id"].startswith("manual-")
    assert store.load_results()[record["job_id"]]["letter"] == "A letter"
