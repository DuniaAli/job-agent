"""
Small helpers for talking to Claude through the Anthropic API.
"""

import json
import re

import anthropic

# Reads ANTHROPIC_API_KEY from the environment (.env file).
_client = None


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def call_claude(model, system_prompt, user_message, max_tokens=2000):
    """Sends one message to Claude and returns the reply as text."""
    client = get_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    print(f"  [tokens: reply used {response.usage.output_tokens} of {max_tokens} allowed, stop reason: {response.stop_reason}]")
    if response.stop_reason == "max_tokens":
        print(f"  WARNING: the reply from {model} was cut off (hit the {max_tokens} token limit)")
    reply_parts = []
    for block in response.content:
        if block.type == "text":
            reply_parts.append(block.text)
    return "".join(reply_parts).strip()


def parse_json_reply(text):
    """
    Claude is asked to reply with JSON only, but sometimes wraps it
    in ```json fences or adds a sentence. This finds the JSON object.
    Returns a dict, or None if no valid JSON is found.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def remove_dashes(text):
    """
    Safety net for the no-dash rule. The prompt already bans dashes;
    this catches any that slip through.
      "2019–2023"         becomes "2019 to 2023"
      "word — word"       becomes "word, word"
      "word - word"       becomes "word, word"
    Normal hyphens inside words (part-time, LLaMA-Factory) are kept.
    """
    text = re.sub(r"(\d)\s*[–—]\s*(\d)", r"\1 to \2", text)
    text = re.sub(r"\s*[–—]\s*", ", ", text)
    text = re.sub(r" - ", ", ", text)
    text = re.sub(r",\s*,", ",", text)
    return text


def count_words(text):
    return len(text.split())
