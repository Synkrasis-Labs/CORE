"""ARE entry point for discovering CORE scenarios."""


def register_scenarios(registry):
    # Importing the module applies ARE's @register_scenario decorator.
    from . import computations, crud  # noqa: F401
