import io
import zipfile
from pathlib import Path

from jobs import run_job

CLIPS = [{"url": f"https://clips.twitch.tv/Clip{i}", "title": f"title {i}", "view_count": 10 - i} for i in range(3)]


def fake_fetch(url, dest_dir, basename, on_progress):
    on_progress(100.0)
    path = Path(dest_dir) / f"{basename}.mp4"
    path.write_bytes(b"v" * 1000)
    return path


def run_synchronously(env, monkeypatch):
    monkeypatch.setattr(env.main, "start_job", lambda job, clips: run_job(job, clips, fetch=fake_fetch))


def test_a_batch_download_returns_one_zip_keeps_files_on_disk_and_cleans_up(env, monkeypatch):
    run_synchronously(env, monkeypatch)
    job_id = env.post("/api/downloads", json={"clips": CLIPS}).json()["job_id"]
    job = env.main.job_store.get(job_id)
    assert job.dir.parent == env.tmp / "jobs"
    assert [p.name for p in job.dir.iterdir()] == ["clips.zip"]
    r = env.get(f"/api/downloads/{job_id}/file")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert sorted(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == ["01_10views_title 0.mp4", "02_9views_title 1.mp4", "03_8views_title 2.mp4"]
    assert env.main.job_store.get(job_id) is None and not job.dir.exists()


def test_only_https_twitch_clip_urls_are_accepted(env):
    for url in ["https://evil.example/x", "http://clips.twitch.tv/x", "https://127.0.0.1/x", "file:///etc/passwd", "https://twitch.tv.evil.example/x"]:
        r = env.post("/api/downloads", json={"clips": [{"url": url, "title": "t", "view_count": 1}]})
        assert r.status_code == 422, url


def test_unknown_and_unfinished_downloads_are_reported_clearly(env, monkeypatch):
    assert env.get("/api/downloads/doesnotexist/file").status_code == 404
    monkeypatch.setattr(env.main, "start_job", lambda job, clips: None)
    job_id = env.post("/api/downloads", json={"clips": CLIPS[:1]}).json()["job_id"]
    assert env.get(f"/api/downloads/{job_id}/file").status_code == 409
