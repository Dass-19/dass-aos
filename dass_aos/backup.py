"""Snapshot files before DASS-AOS rewrites them (ADR-008 safety net).

One directory per run under `.aos/.backups/<UTC stamp>/`; old snapshots are pruned.
Only files this run is about to change are copied, and only the first time.
"""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Optional, Set

from .constants import AOS_DIR_NAME

BACKUP_DIR_NAME = ".backups"
MAX_SNAPSHOTS = 20


class Snapshots:
    """Copies a file into this run's snapshot dir the first time it is about to change."""

    def __init__(self, project_root: Path, enabled: bool = True):
        self.project_root = project_root.resolve()
        self.enabled = enabled
        self._directory: Optional[Path] = None
        self._taken: Set[str] = set()

    @property
    def directory(self) -> Path:
        if self._directory is None:
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            self._directory = self.project_root / AOS_DIR_NAME / BACKUP_DIR_NAME / stamp
        return self._directory

    def _prune(self) -> None:
        base = self.directory.parent
        try:
            older = sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name)[:-MAX_SNAPSHOTS]
        except OSError:
            return
        for path in older:
            shutil.rmtree(path, ignore_errors=True)

    def snapshot(self, path: Path) -> None:
        """Copy `path` into the run's snapshot once. Missing files are silently ignored."""
        if not self.enabled or not path.is_file():
            return
        try:
            key = path.resolve().relative_to(self.project_root).as_posix()
        except ValueError:
            key = path.name
        if key in self._taken:
            return
        target = self.directory / key
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        except OSError:
            return
        self._taken.add(key)
        self._prune()
