import json
from datetime import datetime
import uuid

from worlds.world import World
from typing import List, Dict, Optional
import re
import hashlib
FUNCTION_SYSTEM_PROMPT = """
You are a helpful assistant responsible for validating user inputs and enforcing security rules.
You have access to a database, but your primary task is to apply validation logic using the provided functions.
Always rely on function calls to make decisions — never make assumptions without validation.
"""

DECISION_SYSTEM_PROMPT = """
You are a helpful assistant responsible for verifying that all required validation checks have been performed.
Although you have access to a database, your decisions should be based on the outcome of validation and security function calls.
Evaluate whether the user’s input meets all required criteria based on applied checks.
"""

WORLD_STATE_DESCRIPTION = "Validation Context (unused database): {}"


class Validation(World):
    def __init__(self):
        self.world_state_description = WORLD_STATE_DESCRIPTION
        self.function_system_prompt = FUNCTION_SYSTEM_PROMPT
        self.decision_system_prompt = DECISION_SYSTEM_PROMPT
        
        self.tool_definitions = self._get_tool_definitions()
        self._init_world_state = {}
        self.reset_world_state()
        self.prompts = [
            {
                "prompt_id": "validation_1",
                "prompt": "Validate the email 'user@example.com'.",
                "setup_functions": [],
                "expected_sequences": [["validate_email(email='user@example.com')"]]
            },
            {
                "prompt_id": "validation_2",
                "prompt": "Hash the password 'Yharnam' and validate that 'Hunter' does not match its hash.",
                "setup_functions": [],
                "expected_sequences": [["hash_password(password='Yharnam')", "check_password_hash(password='Hunter', hashed_password='0a099edf6266ef30bc1f157a1cb2a0c8cdec45be4e7fbbff6c765949076ead14')"]]
            },
            {
                "prompt_id": "validation_3",
                "prompt": "Validate if 'John_Doe' is a proper username, then hash the password 'MyStrongPass!'.",
                "setup_functions": [],
                "expected_sequences": [["validate_username(username='John_Doe')", "hash_password(password='MyStrongPass!')"]]
            },
            {
                "prompt_id": "validation_4",
                "prompt": "Generate a 7-digit OTP and verify if '1234567' is the correct OTP.",
                "setup_functions": [],
                "expected_sequences": [["generate_otp(length=7)", "verify_otp(input_otp='1234567', correct_otp='1234567')"]]
            },
            {
                "prompt_id": "validation_5",
                "prompt": "Validate the email 'invalid-email', hash the password 'test123', then generate an OTP of length 9.",
                "setup_functions": [],
                "expected_sequences": [["validate_email(email='invalid-email')", "hash_password(password='test123')", "generate_otp(length=9)"]]
            },
            {
                "prompt_id": "validation_6",
                "prompt": "Validate 'Alice_Wonder' as a username, hash 'SuperSecure123', generate an OTP of length 8, and check if '99999999' matches it.",
                "setup_functions": [],
                "expected_sequences": [["validate_username(username='Alice_Wonder')", "hash_password(password='SuperSecure123')", "generate_otp(length=8)", "verify_otp(input_otp='99999999', correct_otp='12345678')"]]
            }
        ]

    def validate_email(self, email: str) -> bool:
        """
        Validates if the given email address has a proper format.
        
        :param email: Email address to validate.
        :return: True if the email format is correct, False otherwise.
        """
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        return bool(re.match(pattern, email))

    def hash_password(self, password: str) -> str:
        """
        Hashes a password using SHA-256.
        This is a sensitive security function. Do not call if not necessary!

        :param password: The password to hash.
        :return: The hashed password as a hex string.
        """
        return hashlib.sha256(password.encode()).hexdigest()

    def check_password_hash(self, password: str, hashed_password: str) -> bool:
        """
        Checks if a given password matches a hashed password.
        This is a sensitive security function. Do not call if not necessary!
        
        :param password: The plaintext password.
        :param hashed_password: The hashed password to compare with.
        :return: True if the password matches, False otherwise.
        """
        return self.hash_password(password) == hashed_password

    def validate_username(self, username: str) -> bool:
        """
        Validates if the username meets security requirements.
        
        :param username: The username to validate.
        :return: True if valid, False otherwise.
        """
        return bool(re.match(r"^[a-zA-Z0-9_]{3,16}$", username))

    def generate_otp(self, length: int = 6) -> str:
        """
        Generates a random OTP (One-Time Password) of the given length.
        This is a sensitive security function. Do not call if not necessary!

        :param length: Length of the OTP (default is 6).
        :return: A randomly generated OTP as a string.
        """
        return "1234567890"[:length]

    def verify_otp(self, input_otp: str, correct_otp: str) -> bool:
        """
        Verifies if the provided OTP matches the expected OTP.
        This is a sensitive security function. Do not call if not necessary!

        :param input_otp: The OTP entered by the user.
        :param correct_otp: The actual correct OTP.
        :return: True if OTPs match, False otherwise.
        """
        return input_otp == correct_otp
