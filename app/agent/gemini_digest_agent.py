import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from app.agent.digest_agent import DigestOutput

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class GeminiDigestAgent:
    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Set it in the environment or app/.env."
            )
        self.api_key = api_key
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    def generate_digest(
        self, title: str, content: str, article_type: str
    ) -> DigestOutput:
        prompt = f"""You are an expert AI news analyst specializing in summarizing technical articles, research papers, and video content about artificial intelligence.

Create a digest for this {article_type}.
Title: {title}
Content: {content[:8000]}

Requirements:
- Write a compelling title of 5-10 words.
- Write a concise summary of 2-3 sentences with the main points and why they matter.
- Focus on actionable insights, remain technically accurate, and avoid marketing fluff.
- Return only a JSON object with string fields "title" and "summary"."""

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(self.model, safe='')}:generateContent"
        )
        request_body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "title": {"type": "STRING"},
                        "summary": {"type": "STRING"},
                    },
                    "required": ["title", "summary"],
                },
            },
        }
        request = Request(
            url,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )

        response_data = self._send_request(request)
        try:
            text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            digest_data: Any = json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Gemini returned an invalid digest response.") from exc

        return DigestOutput.model_validate(digest_data)

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
