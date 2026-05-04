"""
Small JSON storage helpers used by managers that persist runtime state.
"""

import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Optional


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def atomic_write_json(path: Path, data: Any, lock: Optional[Any] = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_suffix(f"{path.suffix}.tmp")
    context = lock if lock is not None else nullcontext()

    with context:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_file.replace(path)
