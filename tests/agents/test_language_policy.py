"""
Tests for user communication language policy.
"""

from unittest.mock import Mock

from graphs.dev_team.language_policy import (
    resolve_user_language,
    choose_user_text,
    build_user_language_system_instruction,
)
from graphs.dev_team.agents.base import BaseAgent


class _DummyAgent(BaseAgent):
    def invoke(self, state: dict, config=None) -> dict:
        return state


def test_explicit_language_request_has_priority():
    state = {
        "task": "Сделай API для управления задачами",
        "clarification_response": "Please respond in English.",
    }
    assert resolve_user_language(state) == "en"


def test_latest_user_text_language_used_when_no_explicit_request():
    state = {
        "task": "Build a task manager API",
        "clarification_response": "Добавь, пожалуйста, JWT-авторизацию",
    }
    assert resolve_user_language(state) == "ru"


def test_old_explicit_request_persists_until_new_explicit_override():
    state = {
        "task": "Please reply in Russian and create a minimal API",
        "clarification_response": "Also add OpenAPI docs.",
    }
    assert resolve_user_language(state) == "ru"


def test_choose_user_text_returns_russian_when_russian_selected():
    state = {"task": "Ответь на русском и создай API"}
    text = choose_user_text(state, en="Hello", ru="Привет")
    assert text == "Привет"


def test_build_language_instruction_mentions_selected_language():
    state = {"task": "Сделай приложение для заметок"}
    instruction = build_user_language_system_instruction(state)
    assert "Russian" in instruction


def test_base_agent_injects_language_policy_into_system_prompt():
    agent = _DummyAgent(
        name="dummy",
        llm=Mock(),
        prompts={"system": "You are a test agent."},
    )
    state = {"task": "Пиши ответы на русском языке"}
    prompt = agent.create_prompt(state, "Task: {task}")

    system_template = prompt.messages[0].prompt.template
    assert "You are a test agent." in system_template
    assert "User communication language policy" in system_template
    assert "Russian" in system_template
