"""Job queue: add, run, cancel, refuse (no network, no media)."""
import json, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "example_series")


def run_on(root, *args):
    env = dict(os.environ, SERIES_OFFLINE="1")
    env.pop("SERIES_ROOT", None)
    return subprocess.run([sys.executable, "-m", "series_factory", "--series", str(root), "--lang", "en", *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


def _series(tmp_path):
    root = tmp_path / "s"
    shutil.copytree(EXAMPLE, root)
    return root


def test_job_is_queued_run_and_logged(tmp_path):
    root = _series(tmp_path)
    r = run_on(root, "jobs", "--json", "add", "status")
    assert r.returncode == 0, r.stderr
    job = json.loads(r.stdout)
    assert job["state"] == "queued" and job["argv"] == ["status"]
    r = run_on(root, "jobs", "worker", "--once")
    assert r.returncode == 0, r.stderr
    r = run_on(root, "jobs", "log", job["id"], "--json")
    done = json.loads(r.stdout)
    assert done["state"] == "done" and done["code"] == 0 and "$ series status" in done["log"]
    assert job["id"] in run_on(root, "jobs", "list").stdout


def test_failed_command_is_failed_and_next_job_still_runs(tmp_path):
    root = _series(tmp_path)
    a = json.loads(run_on(root, "jobs", "--json", "add", "assemble", "999").stdout)
    b = json.loads(run_on(root, "jobs", "--json", "add", "status").stdout)
    run_on(root, "jobs", "worker", "--once")
    run_on(root, "jobs", "worker", "--once")
    states = {j["id"]: j["state"] for j in json.loads(run_on(root, "jobs", "list", "--json").stdout)}
    assert states[a["id"]] == "failed" and states[b["id"]] == "done"


def test_refused_commands_and_cancel(tmp_path):
    root = _series(tmp_path)
    for bad in (["ui"], ["jobs", "list"], ["nonexistent"], ["--help"]):
        r = run_on(root, "jobs", "add", *bad)
        assert r.returncode != 0
    j = json.loads(run_on(root, "jobs", "--json", "add", "status").stdout)
    run_on(root, "jobs", "cancel", j["id"])
    run_on(root, "jobs", "worker", "--once")
    assert json.loads(run_on(root, "jobs", "log", j["id"], "--json").stdout)["state"] == "cancelled"
