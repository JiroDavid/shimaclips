import zipfile
from pathlib import Path

from jobs import JobStore, job_to_dict, run_job

CLIPS = [
    {"url": f"https://clips.twitch.tv/{i}", "title": f"t{i}", "view_count": 10 - i}
    for i in range(3)
]


def fake_fetch(fail=()):
    def fetch(url, dest_dir, basename, on_progress):
        if url in fail:
            raise RuntimeError("video unavailable")
        on_progress(50.0)
        p = Path(dest_dir) / f"{basename}.mp4"
        p.write_bytes(b"x")
        return p
    return fetch


def test_multiple_clips_are_zipped():
    store = JobStore()
    job = store.create(CLIPS)
    run_job(job, CLIPS, fetch=fake_fetch())
    assert job.status == "done"
    assert job.file_path.suffix == ".zip"
    with zipfile.ZipFile(job.file_path) as z:
        assert sorted(z.namelist()) == [
            "01_10views_t0.mp4", "02_9views_t1.mp4", "03_8views_t2.mp4",
        ]


def test_single_clip_returns_mp4():
    store = JobStore()
    job = store.create(CLIPS[:1])
    run_job(job, CLIPS[:1], fetch=fake_fetch())
    assert job.file_path.suffix == ".mp4"


def test_one_failure_does_not_abort():
    store = JobStore()
    job = store.create(CLIPS)
    run_job(job, CLIPS, fetch=fake_fetch(fail={CLIPS[1]["url"]}))
    assert job.status == "done"
    assert [i.status for i in job.items] == ["done", "failed", "done"]
    assert "unavailable" in job.items[1].error
    with zipfile.ZipFile(job.file_path) as z:
        assert len(z.namelist()) == 2


def test_all_failures_mark_job_error():
    store = JobStore()
    job = store.create(CLIPS)
    run_job(job, CLIPS, fetch=fake_fetch(fail={c["url"] for c in CLIPS}))
    assert job.status == "error"
    assert job.file_path is None


def test_job_to_dict_shape():
    store = JobStore()
    job = store.create(CLIPS[:1])
    d = job_to_dict(job)
    assert d["status"] == "running"
    assert d["items"][0] == {"name": "01_10views_t0", "status": "pending", "percent": 0.0, "error": None}


def test_store_get_and_remove():
    store = JobStore()
    job = store.create(CLIPS[:1])
    assert store.get(job.id) is job
    store.remove(job.id)
    assert store.get(job.id) is None
    assert not job.dir.exists()
