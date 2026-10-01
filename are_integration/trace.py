"""Convert ARE tool events to the saved trace format used by CORE."""

from copy import deepcopy

from are.simulation.types import EventType


def core_artifact(events, final_state, *, driver="ARE scripted oracle; no LLM",
                  world="Computations", app_class="CoreComputationsApp",
                  prompt_id="computations_1",
                  prompt="Add 15 and 7, then multiply the result by 3.", attempts=None):
    """Translate ARE agent events into the existing CORE saved-run schema."""
    workflow = {}
    for event in events:
        if event.event_type != EventType.AGENT or event.app_class_name() != app_class:
            continue
        name = event.function_name()
        args = {key: value for key, value in event.get_args().items() if key != "self"}
        workflow[f"call_{len(workflow) + 1}"] = {
            "op_type": "TOOL",
            "tool_name": f"{world}__{name}",
            "canonical_name": name,
            "tool_args": deepcopy(args),
            "status": "error" if event.failed() else "ok",
            "execution_started": True,
            "content": deepcopy(event.metadata.return_value),
            "error": event.metadata.exception,
            "are_event_id": event.event_id,
            "are_event_time": event.event_time,
        }
    if attempts is not None:
        by_id = {step["are_event_id"]: step for step in workflow.values()}
        ordered = []
        for attempt in attempts:
            if not attempt["tool_name"].startswith(app_class + "__"):
                continue
            step = by_id.pop(attempt["are_event_id"], None)
            if step is None:
                name = attempt["tool_name"].split("__", 1)[1]
                step = {
                    "op_type": "TOOL", "canonical_name": name,
                    "tool_name": f"{world}__{name}",
                    "tool_args": deepcopy(attempt["requested_args"]),
                    "status": "not_observed", "execution_started": False,
                    "content": None, "error": attempt["error"],
                    "are_event_id": None, "are_event_time": None,
                }
            ordered.append(step)
        # Retain events absent from logs, but refuse scoring ambiguous ordering.
        if by_id:
            for step in by_id.values():
                step = {**step, "status": "event_without_attempt_log"}
                ordered.append(step)
        workflow = {f"call_{i}": step for i, step in enumerate(ordered, 1)}
    return {
        "schema_version": 1,
        "world": world,
        "prompt_id": prompt_id,
        "prompt": prompt,
        "driver": driver,
        "final_state": deepcopy(final_state),
        "workflow": workflow,
    }
