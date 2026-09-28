"""Convert ARE tool events to the saved trace format used by CORE."""

from are.simulation.types import EventType


def core_artifact(events, final_state, *, driver="ARE scripted oracle; no LLM"):
    """Translate ARE agent events into the existing CORE saved-run schema."""
    workflow = {}
    for event in events:
        if event.event_type != EventType.AGENT or event.app_class_name() != "CoreComputationsApp":
            continue
        name = event.function_name()
        args = {key: value for key, value in event.get_args().items() if key != "self"}
        workflow[f"call_{len(workflow) + 1}"] = {
            "op_type": "TOOL",
            "tool_name": f"Computations__{name}",
            "canonical_name": name,
            "tool_args": args,
            "status": "error" if event.failed() else "ok",
            "execution_started": True,
            "content": event.metadata.return_value,
            "are_event_id": event.event_id,
            "are_event_time": event.event_time,
        }
    return {
        "schema_version": 1,
        "world": "Computations",
        "prompt_id": "computations_1",
        "prompt": "Add 15 and 7, then multiply the result by 3.",
        "driver": driver,
        "final_state": final_state,
        "workflow": workflow,
    }
