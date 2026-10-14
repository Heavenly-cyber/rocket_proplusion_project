"""Small output contract; benchmark fields arrive only after Stage 04 review."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ReadinessRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    stage: str = "03"
    kind: str = "software_readiness"
    scientific_results: bool = False
    passed: bool
    details: dict


def save_record(path, record):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".new")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(record.model_dump(), indent=2, allow_nan=False) + "\n")
    temporary.replace(destination)
