"""Adapted from FarmAgent rsare/scenarios/scenario/workflow.py."""

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass
class WorkflowStep:
    name: str | None = None
    content: Any = None
    op_type: str = "TOOL"
    tool_name: str | None = None
    canonical_name: str | None = None
    tool_args: dict | None = None
    raw_arguments: str | None = None
    requested_args: Any = None
    tool_call_id: str | None = None
    status: str = "ok"
    error: dict | None = None
    execution_started: bool = False
    depends_on: list[str] = field(default_factory=list)
    time: float | None = None
    time_before: float | None = None
    elapsed_seconds: float = 0.0

    def to_dict(self):
        return asdict(self)


class Workflow:
    def __init__(self):
        self.dag: dict[str, WorkflowStep] = {}

    def __len__(self):
        return len(self.dag)

    def add_node(self, node):
        node = deepcopy(node)
        name = node.name or f"step{len(self.dag)}"
        if name in self.dag:
            raise ValueError(f"Duplicate workflow step: {name}")
        node.name = name
        self.dag[name] = node

    def to_dict(self):
        return {name: step.to_dict() for name, step in self.dag.items()}

    def save_workflow(self, filename):
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, allow_nan=False), encoding="utf-8")

    @classmethod
    def load_workflow(cls, filename):
        workflow = cls()
        for name, data in json.loads(Path(filename).read_text(encoding="utf-8")).items():
            workflow.add_node(WorkflowStep(**{**data, "name": name}))
        return workflow
