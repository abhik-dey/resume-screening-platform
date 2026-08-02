"""Shared fake implementations used across the test suite."""
from app.domain.interfaces.llm_provider import LLMProvider

VALID_PARSED_RESUME_JSON = """{
  "full_name": "Jane Doe",
  "email": "jane.doe@example.com",
  "phone": "555-1234",
  "education": [{"institution": "MIT", "degree": "BSc", "field_of_study": "CS"}],
  "experience": [{"company": "Acme", "title": "Engineer", "description": "Built things"}],
  "projects": [],
  "skills": ["Python", "SQL"],
  "certificates": [],
  "links": {"github": "https://github.com/janedoe"}
}"""


class ScriptedLLMProvider(LLMProvider):
    """Returns responses from a fixed script, one per call, in order.

    Once only one response remains, it keeps returning that one forever —
    convenient both for finite retry-sequence tests (pass exactly the
    responses you want, in order) and as a simple always-succeeds default
    (pass a single-item list) shared across the rest of the test suite.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]
