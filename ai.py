"""Thin wrapper over the OpenAI Platform API (Responses API, with live web search)."""
from __future__ import annotations

import json
import re


def parse_json(text: str) -> dict:
    """Tolerant JSON extraction: strips code fences and any prose around the object."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I | re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            return json.loads(t[start:end + 1])
        raise


class AI:
    """ai.json(prompt) -> dict ; ai.json(prompt, web=True) also lets the model search the web."""

    def __init__(self, api_key: str, model: str = "gpt-4.1", log=None):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.log = log or (lambda *_: None)
        self.web_ok = True

    def _text(self, resp) -> str:
        if getattr(resp, "output_text", None):
            return resp.output_text
        parts = []
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                if getattr(c, "text", None):
                    parts.append(c.text)
        return "\n".join(parts)

    def json(self, prompt: str, system: str = "", web: bool = False, max_tokens: int = 4000) -> dict:
        system = (system or "You are a senior strategist. Output only valid JSON.") + \
                 " Respond with a single JSON object and nothing else."
        kwargs = dict(model=self.model, instructions=system, input=prompt, max_output_tokens=max_tokens)
        if web and self.web_ok:
            for tool in ("web_search", "web_search_preview"):
                try:
                    resp = self.client.responses.create(tools=[{"type": tool}], **kwargs)
                    return parse_json(self._text(resp))
                except json.JSONDecodeError:
                    raise
                except Exception as e:  # tool not available on this model/account
                    self.log(f"Web search via '{tool}' unavailable: {e}")
            self.web_ok = False
            self.log("Continuing without live web search.")
        try:
            resp = self.client.responses.create(text={"format": {"type": "json_object"}}, **kwargs)
        except Exception:
            resp = self.client.responses.create(**kwargs)
        return parse_json(self._text(resp))
