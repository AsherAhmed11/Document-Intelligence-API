import asyncio
from dataclasses import dataclass
import httpx
from langchain_core.embeddings import Embeddings
from app.config import Settings


@dataclass
class EmbeddingResult:
    model_name: str
    vector: list[float]
    dimensions: int


def _parse_hf_response(response_data, model_name: str) -> list[EmbeddingResult]:
    """
    Parse HuggingFace Inference API response into EmbeddingResults.
    HF returns either:
      - 2D list: [[float, ...], [float, ...]]  for batch inputs
      - 3D list: [[[float, ...]], [[float, ...]]]  for some pooled models
    """
    results = []
    for item in response_data:
        # If pooled output is nested: [[vec]] → take item[0]
        vec = item[0] if isinstance(item[0], list) else item
        results.append(EmbeddingResult(
            model_name=model_name,
            vector=vec,
            dimensions=len(vec),
        ))
    return results


class EmbeddingClient:
    """
    Embedding client supporting:
      - huggingface: HuggingFace Inference API (free tier, no local model download)
      - local:       sentence-transformers (requires PyTorch, not suitable for free hosting)
      - openai:      OpenAI Embeddings API
      - bytez:       Bytez API
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.embedding_model
        self.provider = settings.embedding_provider
        self.model = None
        self._openai_client = None

        if self.provider == "local":
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
        elif self.provider == "bytez":
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(
                api_key=settings.bytez_api_key,
                base_url="https://api.bytez.com/models/v2/openai/v1"
            )
        elif self.provider == "openai":
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(
                api_key=settings.openai_api_key
            )
        # huggingface provider: stateless — API key used per-request via httpx

    # ── Sync methods (used by LangChainEmbeddingWrapper / SemanticChunker) ────

    def embed_batch_sync(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch of strings synchronously."""
        if self.provider == "local":
            vectors = self.model.encode(texts, show_progress_bar=False)
            return [
                EmbeddingResult(model_name=self.model_name, vector=vec.tolist(), dimensions=len(vec))
                for vec in vectors
            ]

        elif self.provider == "huggingface":
            url = f"https://api-inference.huggingface.co/models/{self.model_name}"
            headers = {
                "Authorization": f"Bearer {self.settings.hf_api_key}",
                "Content-Type": "application/json",
            }
            # HF Inference API: process in safe batch sizes to avoid timeouts
            all_results: list[EmbeddingResult] = []
            batch_size = 32
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                with httpx.Client(timeout=120.0) as client:
                    response = client.post(url, json={"inputs": batch}, headers=headers)
                    response.raise_for_status()
                all_results.extend(_parse_hf_response(response.json(), self.model_name))
            return all_results

        elif self.provider == "bytez":
            auth_val = self.settings.bytez_api_key or ""
            if auth_val and not auth_val.startswith("Bearer "):
                auth_val = f"Bearer {auth_val}"
            headers = {"Authorization": auth_val, "Content-Type": "application/json"}
            url = "https://api.bytez.com/models/v2/openai/v1/embeddings"
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, json={"model": self.model_name, "input": texts}, headers=headers)
                response.raise_for_status()
                data = response.json()
            return [
                EmbeddingResult(model_name=self.model_name, vector=item["embedding"], dimensions=len(item["embedding"]))
                for item in data["data"]
            ]

        elif self.provider == "openai":
            model_name = "text-embedding-3-large" if "large" in self.model_name.lower() else "text-embedding-3-small"
            headers = {"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"}
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    "https://api.openai.com/v1/embeddings",
                    json={"model": model_name, "input": texts},
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
            return [
                EmbeddingResult(model_name=self.model_name, vector=item["embedding"], dimensions=len(item["embedding"]))
                for item in data["data"]
            ]

        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")

    def embed_sync(self, text: str) -> EmbeddingResult:
        """Embed a single string synchronously."""
        return self.embed_batch_sync([text])[0]

    # ── Async methods (used by DocumentService / QueryService) ────────────────

    async def embed(self, text: str) -> EmbeddingResult:
        """Embed a single string (async wrapper)."""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch of strings (async)."""
        if self.provider == "local":
            vectors = await asyncio.to_thread(self.model.encode, texts, show_progress_bar=False)
            return [
                EmbeddingResult(model_name=self.model_name, vector=vec.tolist(), dimensions=len(vec))
                for vec in vectors
            ]

        elif self.provider == "huggingface":
            url = f"https://api-inference.huggingface.co/models/{self.model_name}"
            headers = {
                "Authorization": f"Bearer {self.settings.hf_api_key}",
                "Content-Type": "application/json",
            }
            all_results: list[EmbeddingResult] = []
            batch_size = 32
            async with httpx.AsyncClient(timeout=120.0) as client:
                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    response = await client.post(url, json={"inputs": batch}, headers=headers)
                    response.raise_for_status()
                    all_results.extend(_parse_hf_response(response.json(), self.model_name))
            return all_results

        elif self.provider in ("bytez", "openai"):
            model_name = self.model_name
            if self.provider == "openai":
                model_name = "text-embedding-3-large" if "large" in self.model_name.lower() else "text-embedding-3-small"
            response = await self._openai_client.embeddings.create(model=model_name, input=texts)
            return [
                EmbeddingResult(model_name=self.model_name, vector=data.embedding, dimensions=len(data.embedding))
                for data in response.data
            ]

        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")


class LangChainEmbeddingWrapper(Embeddings):
    """
    Adapter wrapping EmbeddingClient as a LangChain Embeddings interface
    for SemanticChunker compatibility.
    """

    def __init__(self, client: EmbeddingClient):
        self.client = client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        results = self.client.embed_batch_sync(texts)
        return [r.vector for r in results]

    def embed_query(self, text: str) -> list[float]:
        result = self.client.embed_sync(text)
        return result.vector