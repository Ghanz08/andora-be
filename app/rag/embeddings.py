"""
Embeddings module — wrapper tipis ke OpenAI Embedding API.
Model: text-embedding-3-small (1536 dimensi, murah, kualitas bagus
untuk multilingual termasuk Bahasa Indonesia).
"""

import time
from functools import lru_cache

from openai import OpenAI

from app.config import settings

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536  # harus sama dengan kolom vector(1536) di Supabase



@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(api_key=settings.OPENAI_API_KEY or None)


def get_embedding(text: str, retries: int = 3) -> list[float]:
    """
    Embed 1 teks, return vector list of float.
    Ada retry sederhana kalau kena rate limit / error jaringan sesaat.
    """
    text = text.replace("\n", " ").strip()

    for attempt in range(retries):
        try:
            response = _client().embeddings.create(
                model=EMBEDDING_MODEL,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
            print(f"[embeddings] Error: {e}. Retry dalam {wait}s...")
            time.sleep(wait)


def get_embeddings_batch(texts: list[str], batch_size: int = 50) -> list[list[float]]:
    """
    Embed banyak teks sekaligus. OpenAI API support batch input dalam
    1 request, jadi lebih efisien daripada manggil get_embedding()
    satu-satu dalam loop.
    """
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = [t.replace("\n", " ").strip() for t in texts[i:i + batch_size]]

        response = _client().embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch
        )

        # response.data urutannya dijamin sama dengan urutan input
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

        print(f"[embeddings] Embedded {min(i + batch_size, len(texts))}/{len(texts)} chunks")

    return all_embeddings


if __name__ == "__main__":
    # quick test manual
    sample = "Apa syarat dokumen untuk beasiswa Kaltim Tuntas?"
    vector = get_embedding(sample)
    print(f"Panjang vector: {len(vector)}")
    print(f"5 nilai pertama: {vector[:5]}")