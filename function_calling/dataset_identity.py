"""Explicit, prompt-verified aliases for historical source task IDs."""

# The twelve source tasks and dataset tasks have identical prompts. Preserve
# historical run IDs; expose the resolved dataset ID in revised evaluation.
TRANSACTION_ALIASES = {f'transaction_{i}': f'transactions_{i}' for i in range(1, 13)}


def resolve_record(records, world, prompt_id, prompt=None):
    resolved = TRANSACTION_ALIASES.get(prompt_id, prompt_id) if world == 'transactions' else prompt_id
    matches = [r for r in records if r['world'] == world and r['prompt_id'] == resolved]
    if len(matches) != 1:
        raise ValueError('Task ID must identify exactly one dataset record for this world')
    record = matches[0]
    if prompt is not None and record['prompt'] != prompt:
        raise ValueError('Artifact prompt differs from the dataset task')
    return record
