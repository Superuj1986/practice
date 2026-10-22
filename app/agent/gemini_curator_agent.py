import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from pydantic import ValidationError

from app.agent.curator_agent import (
    CURATOR_PROMPT,
    RankedArticle,
    RankedDigestList,
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class GeminiCuratorAgent:
    def __init__(self, user_profile: dict) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Set it in the environment or app/.env."
            )
        self.api_key = api_key
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.user_profile = user_profile
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        interests = "\n".join(
            f"- {interest}" for interest in self.user_profile["interests"]
        )
        preferences = "\n".join(
            f"- {key}: {value}"
            for key, value in self.user_profile["preferences"].items()
        )
        return f"""{CURATOR_PROMPT}

User Profile:
Name: {self.user_profile["name"]}
Background: {self.user_profile["background"]}
Expertise Level: {self.user_profile["expertise_level"]}

Interests:
{interests}

Preferences:
{preferences}"""

    def rank_digests(self, digests: list[dict]) -> list[RankedArticle]:
        if not digests:
            return []

        digest_list = "\n\n".join(
            f"ID: {digest['id']}\n"
            f"Title: {digest['title']}\n"
            f"Summary: {digest['summary']}\n"
            f"Type: {digest['article_type']}"
            for digest in digests
        )
        prompt = f"""Rank these {len(digests)} AI news digests based on the user profile:

{digest_list}

Return exactly one result for every digest. Use each input ID exactly as given,
with unique ranks from 1 to {len(digests)}. Provide a relevance score from
0.0 to 10.0 and a brief reasoning for each result."""

        response_data = self._send_request(self._build_request(prompt))
        try:
            response_text = response_data["candidates"][0]["content"]["parts"][0][
                "text"
            ]
            ranked_data: Any = json.loads(response_text)
            ranked_list = RankedDigestList.model_validate(ranked_data)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError("Gemini returned an invalid curator response.") from exc

        self._validate_ranking(ranked_list, digests)
        return ranked_list.articles

    def _build_request(self, prompt: str) -> Request:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(self.model, safe='')}:generateContent"
        )
        response_schema = RankedDigestList.model_json_schema()
        response_schema.pop("title", None)
        response_schema.pop("$defs", None)
        response_schema["properties"]["articles"]["items"] = {
            "type": "OBJECT",
            "properties": {
                "digest_id": {"type": "STRING"},
                "relevance_score": {"type": "NUMBER"},
                "rank": {"type": "INTEGER"},
                "reasoning": {"type": "STRING"},
            },
            "required": [
                "digest_id",
                "relevance_score",
                "rank",
                "reasoning",
            ],
        }
        response_schema["type"] = "OBJECT"
        response_schema["properties"]["articles"]["type"] = "ARRAY"
        response_schema["properties"]["articles"].pop("title", None)

        body = {
            "systemInstruction": {
                "parts": [{"text": self.system_prompt}],
            },
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
            },
        }
        return Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )

    @staticmethod
    def _validate_ranking(
        ranked_list: RankedDigestList, digests: list[dict]
    ) -> None:
        expected_ids = [digest["id"] for digest in digests]
        ranked_ids = [article.digest_id for article in ranked_list.articles]
        if len(set(expected_ids)) != len(expected_ids):
            raise ValueError("Input digests contain duplicate IDs.")
        if len(ranked_ids) != len(expected_ids) or set(ranked_ids) != set(expected_ids):
            raise ValueError("Gemini must rank every input digest exactly once.")

        expected_ranks = set(range(1, len(expected_ids) + 1))
        actual_ranks = [article.rank for article in ranked_list.articles]
        if len(set(actual_ranks)) != len(actual_ranks) or set(actual_ranks) != expected_ranks:
            raise ValueError("Gemini must return unique ranks from 1 to the digest count.")

    @staticmethod
    def _send_request(request: Request) -> dict[str, Any]:
        retryable_statuses = {429, 500, 502, 503, 504}
        for attempt in range(3):
            try:
                with urlopen(request, timeout=60) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if exc.code in retryable_statuses and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                details = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Gemini API returned HTTP {exc.code}: {details}"
                ) from exc
            except (URLError, TimeoutError) as exc:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(
                    f"Could not reach the Gemini API: {exc}"
                ) from exc

        raise RuntimeError("Gemini API request failed after retries.")
