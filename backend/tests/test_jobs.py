import os
import time
import zipfile
from pathlib import Path

from jobs import JOB_PREFIX, JobStore, job_to_dict, run_job
from workdir import sweep, work_dir

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


def test_multiple_clips_are_zipped(tmp_path):
    store = JobStore(tmp_path)
    job = store.create(CLIPS)
    run_job(job, CLIPS, fetch=fake_fetch())
    assert job.status == "done"
    assert job.file_path.suffix == ".zip"
    with zipfile.ZipFile(job.file_path) as z:
        assert sorted(z.namelist()) == [
            "01_10views_t0.mp4", "02_9views_t1.mp4", "03_8views_t2.mp4",
        ]


def test_only_the_zip_is_kept_so_a_job_does_not_use_double_the_space(tmp_path):
    store = JobStore(tmp_path)
    job = store.create(CLIPS)
    run_job(job, CLIPS, fetch=fake_fetch())
    assert [p.name for p in job.dir.iterdir()] == ["clips.zip"]


def test_single_clip_returns_mp4(tmp_path):
    store = JobStore(tmp_path)
    job = store.create(CLIPS[:1])
    run_job(job, CLIPS[:1], fetch=fake_fetch())
    assert job.file_path.suffix == ".mp4"


def test_one_failure_does_not_abort(tmp_path):
    store = JobStore(tmp_path)
    job = store.create(CLIPS)
    run_job(job, CLIPS, fetch=fake_fetch(fail={CLIPS[1]["url"]}))
    assert job.status == "done"
    assert [i.status for i in job.items] == ["done", "failed", "done"]
    assert "unavailable" in job.items[1].error
    with zipfile.ZipFile(job.file_path) as z:
        assert len(z.namelist()) == 2


def test_all_failures_mark_job_error(tmp_path):
    store = JobStore(tmp_path)
    job = store.create(CLIPS)
    run_job(job, CLIPS, fetch=fake_fetch(fail={c["url"] for c in CLIPS}))
    assert job.status == "error"
    assert job.file_path is None


def test_job_to_dict_shape(tmp_path):
    store = JobStore(tmp_path)
    job = store.create(CLIPS[:1])
    d = job_to_dict(job)
    assert d["status"] == "running"
    assert d["items"][0] == {"name": "01_10views_t0", "status": "pending", "percent": 0.0, "error": None}


def test_store_get_and_remove(tmp_path):
    store = JobStore(tmp_path)
    job = store.create(CLIPS[:1])
    assert store.get(job.id) is job
    store.remove(job.id)
    assert store.get(job.id) is None
    assert not job.dir.exists()


def test_jobs_live_in_the_work_folder_not_the_system_temp(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIMACLIPS_WORKDIR", str(tmp_path / "work"))
    job = JobStore().create(CLIPS[:1])
    assert job.dir.parent == tmp_path / "work" and work_dir() == tmp_path / "work"


def test_starting_the_server_removes_folders_orphaned_by_an_earlier_run(tmp_path):
    orphan = tmp_path / f"{JOB_PREFIX}abc123"
    orphan.mkdir()
    (orphan / "clips.zip").write_bytes(b"x" * 10)
    unrelated = tmp_path / "keep_me"
    unrelated.mkdir()
    JobStore(tmp_path)
    assert not orphan.exists() and unrelated.exists()


def test_sweep_only_removes_folders_older_than_the_limit(tmp_path):
    old, fresh = tmp_path / "shimaclips_tr_old", tmp_path / "shimaclips_tr_fresh"
    old.mkdir()
    fresh.mkdir()
    long_ago = time.time() - 7200
    os.utime(old, (long_ago, long_ago))
    assert sweep("shimaclips_tr_", tmp_path, older_than=3600) == 1
    assert not old.exists() and fresh.exists()
