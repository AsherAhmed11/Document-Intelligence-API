import asyncio
from dataclasses import dataclass
from typing import Optional
import httpx
from langchain_core.embeddings import Embeddings
from app.config import Settings

@dataclass
class EmbeddingResult:
    model_name: str 
    vector: list[float]
    dimensions: int


class EmbeddingClient:
    """
    Wrapper around sentence-transformers / OpenAI / Bytez embedding APIs.
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

    def embed_batch_sync(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch of strings synchronously."""
        if self.provider == "local":
            vectors = self.model.encode(texts, show_progress_bar=False)
            return [
                EmbeddingResult(
                    model_name=self.model_name,
                    vector=vec.tolist(),
                    dimensions=len(vec),
                )
                for vec in vectors
            ]
        elif self.provider == "bytez":
            headers = {
                "Authorization": f"Bearer {self.settings.bytez_api_key}" if self.settings.bytez_api_key and not self.settings.bytez_api_key.startswith("Bearer") else self.settings.bytez_api_key,
                "Content-Type": "application/json"
            }
            # Make sure we clean up the authorization header if needed
            auth_val = self.settings.bytez_api_key or ""
            if auth_val and not auth_val.startswith("Bearer "):
                auth_val = f"Bearer {auth_val}"
            headers["Authorization"] = auth_val

            url = "https://api.bytez.com/models/v2/openai/v1/embeddings"
            payload = {
                "model": self.model_name,
                "input": texts
            }
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            return [
                EmbeddingResult(
                    model_name=self.model_name,
                    vector=item["embedding"],
                    dimensions=len(item["embedding"]),
                )
                for item in data["data"]
            ]
        elif self.provider == "openai":
            headers = {
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json"
            }
            url = "https://api.openai.com/v1/embeddings"
            model_name = "text-embedding-3-small"
            if "large" in self.model_name.lower():
                model_name = "text-embedding-3-large"
            payload = {
                "model": model_name,
                "input": texts
            }
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            return [
                EmbeddingResult(
                    model_name=self.model_name,
                    vector=item["embedding"],
                    dimensions=len(item["embedding"]),
                )
                for item in data["data"]
            ]
        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")

    def embed_sync(self, text: str) -> EmbeddingResult:
        """Embed a single string synchronously."""
        return self.embed_batch_sync([text])[0]

    async def embed(self, text: str) -> EmbeddingResult:
        """Embed a single string (async wrapper)."""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed a batch of strings (async)."""
        if self.provider == "local":
            vectors = await asyncio.to_thread(
                self.model.encode, texts, show_progress_bar=False
            )
            return [
                EmbeddingResult(
                    model_name=self.model_name,
                    vector=vec.tolist(),
                    dimensions=len(vec),
                )
                for vec in vectors
            ]
        elif self.provider in ("bytez", "openai"):
            model_name = self.model_name
            if self.provider == "openai":
                if "large" in self.model_name.lower():
                    model_name = "text-embedding-3-large"
                else:
                    model_name = "text-embedding-3-small"
            
            response = await self._openai_client.embeddings.create(
                model=model_name,
                input=texts
            )
            return [
                EmbeddingResult(
                    model_name=self.model_name,
                    vector=data.embedding,
                    dimensions=len(data.embedding),
                )
                for data in response.data
            ]
        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")


class LangChainEmbeddingWrapper(Embeddings):
    """
    Adapter class to wrap EmbeddingClient as a LangChain Embeddings model
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