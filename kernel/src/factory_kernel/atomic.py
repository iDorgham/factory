"""Atomic file writes and JSON helpers."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Union


def atomic_write(path: Union[str, Path], data: str | bytes, mode: str = "w") -> None:
    """Write data atomically: temp file in same dir → fsync → rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    dir_fd = os.open(str(path.parent), os.O_RDONLY)
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_")
        try:
            if isinstance(data, str):
                os.write(fd, data.encode("utf-8"))
            else:
                os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.rename(tmp_name, str(path))
        os.fsync(dir_fd)  # ensure directory entry is durable
    finally:
        os.close(dir_fd)


def atomic_write_json(path: Union[str, Path], obj: Any, indent: int = 2) -> None:
    """Serialize and atomically write JSON."""
    text = json.dumps(obj, indent=indent, ensure_ascii=False, sort_keys=True) + "\n"
    atomic_write(path, text)


def append_jsonl(path: Union[str, Path], obj: Any) -> None:
    """Append one JSON object as a line (not fully atomic across processes,
    but safe under lease + fencing)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def read_json(path: Union[str, Path], default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path: Union[str, Path]) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events
