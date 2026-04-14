import logging

from google import genai
from google.genai import types

from app.config import get_settings


logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.gemini_api_key.strip():
            raise RuntimeError("GEMINI_API_KEY is missing.")
        self.client = genai.Client(api_key=self.settings.gemini_api_key)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        logger.info("Embedding %s text chunks", len(texts))

        try:
            response = self.client.models.embed_content(
                model=self.settings.gemini_embedding_model,
                contents=texts,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.settings.embedding_dimensions,
                    task_type="RETRIEVAL_DOCUMENT",
                ),
            )
        except Exception as exc:
            logger.exception("Embedding request failed")
            raise RuntimeError(f"Embedding request failed: {exc}") from exc

        vectors = [item.values for item in response.embeddings]
        logger.info("Generated %s embeddings", len(vectors))
        return vectors

    def embed_query(self, query: str) -> list[float]:
        logger.info("Embedding retrieval query")
        try:
            response = self.client.models.embed_content(
                model=self.settings.gemini_embedding_model,
                contents=query,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.settings.embedding_dimensions,
                    task_type="RETRIEVAL_QUERY",
                ),
            )
        except Exception as exc:
            logger.exception("Query embedding request failed")
            raise RuntimeError(f"Query embedding request failed: {exc}") from exc

        return response.embeddings[0].values
