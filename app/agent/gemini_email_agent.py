import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from pydantic import ValidationError

from app.agent.email_agent import (
    EMAIL_PROMPT,
    EmailDigestResponse,
    EmailIntroduction,
    RankedArticleDetail,
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class GeminiEmailAgent:
    def __init__(self, user_profile: dict) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Set it in the environment or app/.env."
            )
        self.api_key = api_key
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.user_profile = user_profile

    def generate_introduction(
        self, ranked_articles: list[RankedArticleDetail]
    ) -> EmailIntroduction:
        current_date = datetime.now().strftime("%B %d, %Y")
        user_name = self.user_profile["name"]
        if not ranked_articles:
            return EmailIntroduction(
                greeting=(
                    f"Hey {user_name}, here is your daily digest of AI news "
                    f"for {current_date}."
                ),
                introduction="No articles were ranked today.",
            )

        article_summaries = "\n".join(
            f"{index}. {article.title} "
            f"(Score: {article.relevance_score:.1f}/10)"
            for index, article in enumerate(ranked_articles[:10], start=1)
        )
        prompt = f"""Create an email introduction for {user_name} for {current_date}.

Top ranked articles:
{article_summaries}

Generate a greeting and a concise introduction that previews these articles.
The greeting must start exactly with "Hey {user_name}".
The introduction should be 2-3 sentences, warm, and professional.
Return only a JSON object with string fields "greeting" and "introduction"."""

        response_data = self._send_request(self._build_request(prompt))
        try:
            response_text = response_data["candidates"][0]["content"]["parts"][0][
                "text"
            ]
            introduction = EmailIntroduction.model_validate(json.loads(response_text))
        except (
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            raise RuntimeError("Gemini returned an invalid email introduction.") from exc

        if not introduction.greeting.startswith(f"Hey {user_name}"):
            introduction.greeting = (
                f"Hey {user_name}, here is your daily digest of AI news "
                f"for {current_date}."
            )
        return introduction

    def create_email_digest_response(
        self,
        ranked_articles: list[RankedArticleDetail],
        total_ranked: int,
        limit: int = 10,
    ) -> EmailDigestResponse:
        top_articles = ranked_articles[:limit]
        return EmailDigestResponse(
            introduction=self.generate_introduction(top_articles),
            articles=top_articles,
            total_ranked=total_ranked,
            top_n=limit,
        )

    def _build_request(self, prompt: str) -> Request:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(self.model, safe='')}:generateContent"
        )
        body = {
            "systemInstruction": {"parts": [{"text": EMAIL_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "greeting": {"type": "STRING"},
                        "introduction": {"type": "STRING"},
                    },
                    "required": ["greeting", "introduction"],
                },
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
