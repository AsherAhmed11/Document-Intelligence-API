"""
EmbeddingClient — supports Google Gemini (primary) via the new google-genai SDK.

For Railway free tier: use EMBEDDING_PROVIDER=gemini
  → calls Google's servers, zero local RAM, gemini-embedding-001 (3072-dim)

For local dev without internet: use EMBEDDING_PROVIDER=local
  → requires sentence-transformers installed, uses ~90MB RAM
"""
import asyncio
from dataclasses import dataclass
from app.config import Settings


@dataclass
class EmbeddingResult:
    model_name: str
    vector: list[float]
    dimensions: int


class EmbeddingClient:
    """
    Unified embedding client. Provider is selected via settings.embedding_provider.

    Supported providers:
      - gemini : Google Gemini gemini-embedding-001 (recommended, free, remote, 3072-dim)
      - local  : sentence-transformers (local, needs PyTorch — not for Railway free tier)
      - openai : OpenAI text-embedding-3-small/large
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.embedding_model
        self.provider = settings.embedding_provider
        self._local_model = None
        self._gemini_client = None

        if self.provider == "gemini":
            from google import genai
            self._gemini_client = genai.Client(api_key=settings.gemini_api_key)

        elif self.provider == "local":
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer(self.model_name)

        elif self.provider == "openai":
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    # ── Sync embed batch (called during chunking/sync contexts) ──────────────

    def embed_batch_sync(self, texts: list[str]) -> list[EmbeddingResult]:
        """Synchronous batch embed."""
        if self.provider == "gemini":
            return self._gemini_embed_batch_sync(texts)

        elif self.provider == "local":
            vectors = self._local_model.encode(texts, show_progress_bar=False)
            return [
                EmbeddingResult(model_name=self.model_name, vector=vec.tolist(), dimensions=len(vec))
                for vec in vectors
            ]

        elif self.provider == "openai":
            import httpx
            model_name = "text-embedding-3-large" if "large" in self.model_name.lower() else "text-embedding-3-small"
            with httpx.Client(timeout=60.0) as client:
                r = client.post(
                    "https://api.openai.com/v1/embeddings",
                    json={"model": model_name, "input": texts},
                    headers={"Authorization": f"Bearer {self.settings.openai_api_key}"}
                )
                r.raise_for_status()
            return [
                EmbeddingResult(model_name=self.model_name, vector=item["embedding"], dimensions=len(item["embedding"]))
                for item in r.json()["data"]
            ]

        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")

    def embed_sync(self, text: str) -> EmbeddingResult:
        """Embed a single string synchronously."""
        return self.embed_batch_sync([text])[0]

    # ── Gemini-specific helpers ───────────────────────────────────────────────

    def _gemini_embed_batch_sync(self, texts: list[str]) -> list[EmbeddingResult]:
        """
        Batch embed using Gemini gemini-embedding-001.
        Processes in batches of 100 (API limit).
        """
        results = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            response = self._gemini_client.models.embed_content(
                model=self.model_name,
                contents=batch,
            )
            for emb in response.embeddings:
                vec = list(emb.values)
                results.append(EmbeddingResult(
                    model_name=self.model_name,
                    vector=vec,
                    dimensions=len(vec),
                ))
        return results

    # ── Async wrappers (used by DocumentService / QueryService) ─────────────

    async def embed(self, text: str) -> EmbeddingResult:
        """Embed a single string (async)."""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch of strings (async — wraps sync in thread pool)."""
        return await asyncio.to_thread(self.embed_batch_sync, texts)