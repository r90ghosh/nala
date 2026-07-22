import subprocess
from pathlib import Path

from nala.config import PROJECTS
from nala.watchers.git import GitWatcher


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def test_first_poll_no_signal_for_clean_repo(monkeypatch, data_dir, tmp_path):
    root = tmp_path / "projects"
    _init_repo(root / PROJECTS[0])
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(root))

    signals = GitWatcher().poll()

    assert signals == []


def test_becoming_dirty_signals_once_not_on_repoll(monkeypatch, data_dir, tmp_path):
    root = tmp_path / "projects"
    repo = root / PROJECTS[0]
    _init_repo(repo)
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(root))

    watcher = GitWatcher()
    watcher.poll()  # baseline: clean, no signal

    (repo / "new_file.txt").write_text("dirty now")
    first = watcher.poll()
    second = watcher.poll()

    assert len(first) == 1
    assert first[0].kind == "newly_dirty"
    assert second == []  # no duplicate signal on re-poll — still dirty, not a change


def test_first_poll_signals_if_already_dirty(monkeypatch, data_dir, tmp_path):
    root = tmp_path / "projects"
    repo = root / PROJECTS[0]
    _init_repo(repo)
    (repo / "uncommitted.txt").write_text("oops")
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(root))

    signals = GitWatcher().poll()

    assert len(signals) == 1
    assert signals[0].kind == "dirty_or_diverged"


def test_non_git_dirs_are_skipped_entirely(monkeypatch, data_dir, tmp_path):
    root = tmp_path / "projects"
    root.mkdir()  # none of PROJECTS exist as real repos here
    monkeypatch.setenv("NALA_PROJECTS_ROOT", str(root))

    signals = GitWatcher().poll()

    assert signals == []
