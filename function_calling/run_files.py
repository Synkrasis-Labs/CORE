"""Default locations for local run artifacts."""

from datetime import datetime, timezone
from pathlib import Path
import re


def new_run_path(task, model):
    label = re.sub(r"[^A-Za-z0-9_.-]", "_", model)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S_%fZ")
    folder = Path("runs") / task / f"{stamp}_{label}"
    folder.mkdir(parents=True, exist_ok=False)
    return folder / "run.json"
