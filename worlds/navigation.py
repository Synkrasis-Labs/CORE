# navigation.py

from typing import Tuple, Dict, List, Optional
from worlds.world import World
from llm_tool import tool

FUNCTION_SYSTEM_PROMPT= """
You are an AI agent responsible for handling spatial navigation in a 5x5 grid-based environment.
Your objective is to correctly execute movement functions to navigate the grid efficiently while ensuring logical consistency.
"""
DECISION_SYSTEM_PROMPT="""
You are a helpful assistant that makes changes on a database. The database is a list of messages. Always check the database.
"""

class Navigation(World):
    def __init__(self):
        self.world_state_description = "Player Position on 5x5 Grid: {}"
        self.function_system_prompt = FUNCTION_SYSTEM_PROMPT
        self.decision_system_prompt = DECISION_SYSTEM_PROMPT

        self.grid_size = (5, 5) 
        self._init_world_state = {
            "player_position": (0, 0),
        }
        self.reset_world_state()

        self.prompts = [
            {
                "prompt_id": "navigation_1",
                "prompt": "Move the player right by 2 steps.", 
                "setup_functions": [],
                "expected_sequences": [["move_right(2)"]]
            },
            {
                "prompt_id": "navigation_2",
                "prompt": "Move the player down by 3 steps, then retrieve the player's position.", 
                "setup_functions": [],
                "expected_sequences": [["move_down(3)", "get_player_position()"]]
            },
            {
                "prompt_id": "navigation_3",
                "prompt": "Move the player right by 1 step, then move down by 2 steps.", 
                "setup_functions": [],
                "expected_sequences": [["move_right(1)", "move_down(2)"]]
            },
            {
                "prompt_id": "navigation_4",
                "prompt": "Move the player in a square pattern (2 steps right, 2 steps down, 2 steps left, 2 steps up).",
                "setup_functions": [], 
                "expected_sequences": [["move_right(2)", "move_down(2)", "move_left(2)", "move_up(2)"]]
            },
            {
                "prompt_id": "navigation_5",
                "prompt": "Move the player to the bottom-right corner of the grid (4,4) as fast as possible.",
                "setup_functions": [], 
                "expected_sequences": [["move_right(4)", "move_down(4)"]]
            },
            {
                "prompt_id": "navigation_6",
                "prompt": "Move the player right by 3 steps. Reset the player's position and confirm their location.",
                "setup_functions": [], 
                "expected_sequences": [["move_right(3)", "reset_position()", "get_player_position()"]]
            }
        ]      

        self.tool_definitions = self._get_tool_definitions()

    def is_within_bounds(self, position: Tuple[int, int]) -> bool:
        """
        Checks if a given position is within the grid bounds.
        
        :param position: The (x, y) position to check.
        :return: True if within bounds, False otherwise.
        """
        grid_width, grid_height = self.grid_size
        x, y = position
        return 0 <= x < grid_width and 0 <= y < grid_height

    @tool()
    def move_up(self, steps: int = 1) -> str:
        """
        Moves the player up by a specified number of steps.
        
        :param steps: The number of steps to move (default: 1).
        :return: Confirmation message.
        """
        x, y = self.world_state["player_position"]
        new_position = (x, y - steps)
        if self.is_within_bounds(new_position):
            self.world_state["player_position"] = new_position
            return f"Moved up to {new_position}."
        return "Move out of bounds."

    @tool()
    def move_down(self, steps: int = 1) -> str:
        """
        Moves the player down by a specified number of steps.
        
        :param steps: The number of steps to move (default: 1).
        :return: Confirmation message.
        """
        x, y = self.world_state["player_position"]
        new_position = (x, y + steps)
        if self.is_within_bounds(new_position):
            self.world_state["player_position"] = new_position
            return f"Moved down to {new_position}."
        return "Move out of bounds."

    @tool()
    def move_left(self,steps: int = 1) -> str:
        """
        Moves the player left by a specified number of steps.
        
        :param steps: The number of steps to move (default: 1).
        :return: Confirmation message.
        """
        x, y = self.world_state["player_position"]
        new_position = (x - steps, y)
        if self.is_within_bounds(new_position):
            self.world_state["player_position"] = new_position
            return f"Moved left to {new_position}."
        return "Move out of bounds."

    @tool()
    def move_right(self,steps: int = 1) -> str:
        """
        Moves the player right by a specified number of steps.
        
        :param steps: The number of steps to move (default: 1).
        :return: Confirmation message.
        """
        x, y = self.world_state["player_position"]
        new_position = (x + steps, y)
        if self.is_within_bounds(new_position):
            self.world_state["player_position"] = new_position
            return f"Moved right to {new_position}."
        return "Move out of bounds."

    @tool()
    def get_player_position(self) -> Tuple[int, int]:
        """
        Retrieves the current position of the player.
        
        :return: The (x, y) coordinates of the player.
        """
        return self.world_state["player_position"]

    @tool()
    def reset_position(self) -> str:
        """
        Resets the player to the starting position.
        
        :return: Confirmation message.
        """
        self.world_state["player_position"] = (0, 0)
        return "Player position reset to (0, 0)."
