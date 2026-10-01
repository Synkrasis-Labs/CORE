import json
from datetime import datetime
import uuid

from worlds.world import World
from typing import List, Dict, Optional

FUNCTION_SYSTEM_PROMPT="""
You are a helpful assistant that is responsible for performing computational and mathematical operations. The database of calculations is provided. Always check the state and use the functions to make changes based on the user prompt.
"""
DECISION_SYSTEM_PROMPT="""
You are a helpful assistant that is responsible for performing computational and mathematical operations. The database of calculations is provided.
"""
WORLD_STATE_DESCRIPTION = "Database: {}"

class Computations(World):
    def __init__(self):
        self.world_state_description = WORLD_STATE_DESCRIPTION
        self.function_system_prompt = FUNCTION_SYSTEM_PROMPT
        self.decision_system_prompt = DECISION_SYSTEM_PROMPT
        
        self.tool_definitions = self._get_tool_definitions()
        self._init_world_state = {
            "calculations": []
        }
        self.reset_world_state()
        self.prompts = [
            {
                "prompt_id": "computations_1",
                "prompt": "Add 15 and 7, then multiply the result by 3.",
                "setup_functions": [],
                "expected_sequences": [["add_numbers(a=15, b=7)", "multiply_numbers(a=22, b=3)"]]
            },
            {
                "prompt_id": "computations_2",
                "prompt": "Divide 100 by 4, then raise the result to the power of 2.",
                "setup_functions": [],
                "expected_sequences": [["divide_numbers(a=100, b=4)", "power(base=25, exponent=2)"]]
            },
            {
                "prompt_id": "computations_3",
                "prompt": "Calculate the average of the numbers 10, 20, and 30.",
                "setup_functions": [],
                "expected_sequences": [["calculate_average(numbers=[10, 20, 30])"]]
            },
            {
                "prompt_id": "computations_4",
                "prompt": "Subtract 4 from 25 and divide the result by 3. Then, calculate the average of this quotient and the product of 4 and 5.",
                "setup_functions": [],
                "expected_sequences": [["subtract_numbers(a=25, b=4)", "divide_numbers(a=21, b=3)", "multiply_numbers(a=4, b=5)", "calculate_average(numbers=[7,20])"]]
            },
            {
                "prompt_id": "computations_5",
                "prompt": "Multiply 6 by 7. Then, add 8 to the product. Then, divide the result by 4 raised to the second power.",
                "setup_functions": [],
                "expected_sequences": [["multiply_numbers(a=6, b=7)", "add_numbers(a=42, b=8)","power(base=4, exponent=2)", "divide_numbers(a=50, b=16)"]]
            }
        ]

    def add_numbers(self, a: int, b: int) -> int:
        """
        Adds two integers and returns the result.
        
        :param a: The first integer.
        :param b: The second integer.
        :return: Sum of a and b.
        """
        self.world_state["calculations"].append(f"{a} + {b} = {a + b}")
        return a + b

    def subtract_numbers(self, a: int, b: int) -> int:
        """
        Subtracts the second integer from the first and returns the result.
        
        :param a: The first integer.
        :param b: The second integer.
        :return: Difference of a and b.
        """
        self.world_state["calculations"].append(f"{a} - {b} = {a - b}")
        return a - b

    def multiply_numbers(self, a: int, b: int) -> int:
        """
        Multiplies two integers and returns the product.
        
        :param a: The first integer.
        :param b: The second integer.
        :return: Product of a and b.
        """
        self.world_state["calculations"].append(f"{a} * {b} = {a * b}")
        return a * b

    def divide_numbers(self, a: int, b: int) -> Optional[float]:
        """
        Divides the first integer by the second and returns the result.
        
        :param a: The numerator.
        :param b: The denominator. Must not be zero.
        :return: Quotient of a and b, or None if division by zero.
        """
        self.world_state["calculations"].append(f"{a} / {b} = {a / b if b != 0 else None}")
        if b == 0:
            return None
        return a / b

    def power(self, base: int, exponent: int) -> int:
        """
        Raises a base number to a given exponent and returns the result.
        
        :param base: The base number.
        :param exponent: The exponent to raise the base to.
        :return: base raised to the power of exponent.
        """
        self.world_state["calculations"].append(f"{base} ^ {exponent} = {base ** exponent}")
        return base ** exponent

    def calculate_average(self, numbers: List[int]) -> float:
        """
        Calculates the average of a list of integers.
        
        :param numbers: A list of integers.
        :return: The average value.
        """
        self.world_state["calculations"].append(f"Average of {numbers} = {sum(numbers) / len(numbers) if numbers else 0.0}")
        if not numbers:
            return 0.0
        return sum(numbers) / len(numbers)
