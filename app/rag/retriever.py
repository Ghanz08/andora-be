"""
Retriever module — terima query teks, embed, cari chunk paling relevan
dari Supabase (pgvector), DIFILTER berdasarkan source_document (program
beasiswa) supaya gak ketuker antar dokumen.
"""

from app.rag.embeddings import get_embedding
from app.integrations.supabase_client import get_supabase_client

supabase = get_supabase_client()


def retrieve(query: str, program: str, top_k: int = 3) -> list[dict]:
    """
    Cari chunk paling relevan dari 1 program beasiswa spesifik.

    Args:
        query: pertanyaan/topik yang dicari
        program: source_document yang jadi filter wajib, misal "kaltim_tuntas"
        top_k: jumlah chunk teratas yang diambil

    Returns:
        list of dict: [{"content": ..., "metadata": ..., "similarity": ...}, ...]
    """
    query_embedding = get_embedding(query)

    result = supabase.rpc("match_document_chunks", {
        "query_embedding": query_embedding,
        "match_count": top_k,
        "filter_source": program
    }).execute()

    return result.data or []


def format_context(results: list[dict]) -> str:
    """
    Gabungin hasil retrieval jadi 1 blok teks context,
    siap di-inject ke prompt/tool response buat LLM.
    """
    if not results:
        return "Tidak ditemukan informasi relevan di basis pengetahuan."

    parts = []
    for r in results:
        heading = r.get("metadata", {}).get("heading", "")
        parts.append(f"[{heading}]\n{r['content']}")

    return "\n\n---\n\n".join(parts)


if __name__ == "__main__":
    # quick test manual
    results = retrieve("apa syarat dokumen yang dibutuhkan mahasiswa?", program="kaltim_tuntas")
    print(f"Ditemukan {len(results)} hasil\n")
    print(format_context(results))