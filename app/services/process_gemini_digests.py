import logging
from typing import Optional

from app.agent.gemini_digest_agent import GeminiDigestAgent
from app.database.repository import Repository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def process_gemini_digests(limit: Optional[int] = None) -> dict[str, int]:
    agent = GeminiDigestAgent()
    repo = Repository()
    articles = repo.get_articles_without_digest(limit=limit)
    processed = 0
    failed = 0

    logger.info("Starting Gemini digest processing for %s articles", len(articles))
    for index, article in enumerate(articles, 1):
        article_type = article["type"]
        article_id = article["id"]
        try:
            digest = agent.generate_digest(
                title=article["title"],
                content=article["content"],
                article_type=article_type,
            )
            repo.create_digest(
                article_type=article_type,
                article_id=article_id,
                url=article["url"],
                title=digest.title,
                summary=digest.summary,
                published_at=article.get("published_at"),
            )
            processed += 1
            logger.info(
                "[%s/%s] Created Gemini digest for %s %s",
                index,
                len(articles),
                article_type,
                article_id,
            )
        except Exception:
            failed += 1
            logger.exception(
                "[%s/%s] Failed to create Gemini digest for %s %s",
                index,
                len(articles),
                article_type,
                article_id,
            )

    result = {"total": len(articles), "processed": processed, "failed": failed}
    logger.info("Gemini digest processing complete: %s", result)
    return result


if __name__ == "__main__":
    print(process_gemini_digests())
