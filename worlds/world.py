from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class World:
    tool_definitions: List[Dict]
    prompts: List[Dict]
    world_state: Dict
    _init_world_state: Dict
    world_state_description: str
    function_system_prompt: str
    decision_system_prompt: str

    def _get_tool_definitions(self) -> List[Dict]:
        # Only the legacy schema path needs this optional dependency.
        from llm_tool import tool

        methods = [
            i for i in dir(self)
            if not i.startswith('_') and
            type(getattr(self, i)) == type(self._get_tool_definitions) and
            i not in dir(World)
        ]
        
        return [
            tool()(getattr(self, i)).definition for i in methods
        ]
        
    def reset_world_state(self):
        self.world_state = self._init_world_state.copy()
