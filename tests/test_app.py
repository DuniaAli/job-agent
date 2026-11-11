import os

from streamlit.testing.v1 import AppTest

import pipeline
import store

APP_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


def seed(tmp_path, monkeypatch, statuses_and_scores):
    path = str(tmp_path / "results.json")
    monkeypatch.setattr(store, "RESULTS_FILE", path)
    number = 0
    for status, score in statuses_and_scores:
        job = {"job_id": f"j{number}", "company": f"Co{number}", "title": "Role", "location": "",
               "url": "", "description": "", "source": "test"}
        result = {"score": score, "verdict": "maybe", "reasons": [], "red_flags": [], "hard_blockers": []}
        store.add_record(store.make_record(job, result, status))
        number = number + 1


def test_page_loads_with_no_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "RESULTS_FILE", str(tmp_path / "results.json"))
    at = AppTest.from_file(APP_FILE, default_timeout=20).run()
    assert not at.exception
    assert "No jobs yet" in at.info[0].value


def test_summary_counts(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch, [
        (store.STATUS_READY, 80), (store.STATUS_READY, 60), (store.STATUS_APPLIED, 70),
        (store.STATUS_NEEDS_ATTENTION, 50),
    ])
    at = AppTest.from_file(APP_FILE, default_timeout=20).run()
    assert not at.exception
    values = {}
    for metric in at.metric:
        values[metric.label] = metric.value
    assert values["To review"] == "2"
    assert values["Needs attention"] == "1"
    assert values["Applied"] == "1"
    assert values["Average score"] == "65"


def test_run_button_shows_result_message(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch, [(store.STATUS_READY, 80)])

    def fake_run(limit, use_sheet, progress):
        progress("working")
        return {"found": 3, "scored": 3, "letters": 1, "failed": 0}

    monkeypatch.setattr(pipeline, "run_pipeline", fake_run)
    at = AppTest.from_file(APP_FILE, default_timeout=20).run()
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert "Scored 3 jobs, wrote 1 letters" in at.success[0].value


def test_search_filter_hides_non_matches(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch, [(store.STATUS_READY, 80), (store.STATUS_READY, 60)])
    at = AppTest.from_file(APP_FILE, default_timeout=20).run()
    at.sidebar.text_input[0].set_value("Co1").run()
    assert not at.exception
    assert "1 jobs" in at.caption[0].value
