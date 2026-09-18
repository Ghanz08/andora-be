"""
Ingestion module — orkestrator: PDF -> chunking -> embedding -> simpan ke Supabase.
Dijalankan manual sekali per dokumen (bukan bagian dari runtime app).
"""

from app.rag.chunking import chunk_document
from app.rag.embeddings import get_embeddings_batch
from app.integrations.supabase_client import get_supabase_client

supabase = get_supabase_client()


def ingest_document(source_path: str, source_name: str, is_pdf: bool = True) -> int:
    """
    Proses 1 dokumen end-to-end: chunk -> embed -> insert ke document_chunks.
    Return jumlah chunk yang berhasil disimpan.
    """
    print(f"[ingestion] Mulai proses: {source_path} (source_name='{source_name}')")

    # 1. Chunking
    chunks = chunk_document(source_path, source_name, is_pdf=is_pdf)
    print(f"[ingestion] Dapat {len(chunks)} chunks")

    if not chunks:
        print("[ingestion] Tidak ada chunk dihasilkan, proses dihentikan.")
        return 0

    # 2. Hapus dulu chunk lama dari source_name yang sama, biar aman
    #    kalau script ini dijalankan ulang (re-ingest), gak dobel data.
    supabase.table("document_chunks").delete().eq("source_document", source_name).execute()
    print(f"[ingestion] Chunk lama untuk '{source_name}' (kalau ada) sudah dihapus")

    # 3. Embedding — kirim semua isi chunk sekaligus (batch), lebih efisien
    texts = [c.content for c in chunks]
    embeddings = get_embeddings_batch(texts)

    # 4. Gabungkan tiap chunk dengan embedding-nya, siapkan buat insert
    rows = []
    for chunk, embedding in zip(chunks, embeddings):
        rows.append({
            "source_document": source_name,
            "content": chunk.content,
            "embedding": embedding,
            "metadata": chunk.metadata,
        })

    # 5. Insert ke Supabase (sekaligus dalam 1 batch call)
    result = supabase.table("document_chunks").insert(rows).execute()
    inserted_count = len(result.data) if result.data else 0

    print(f"[ingestion] Selesai. {inserted_count} chunks tersimpan ke Supabase.\n")
    return inserted_count


def ingest_all(documents: list[dict]) -> None:
    """
    Proses beberapa dokumen sekaligus.
    documents = [
        {"path": "data/juknis_kaltim_tuntas.pdf", "source_name": "kaltim_tuntas"},
        {"path": "data/juknis_beasiswa_unggulan.pdf", "source_name": "beasiswa_unggulan"},
    ]
    """
    total = 0
    for doc in documents:
        count = ingest_document(
            source_path=doc["path"],
            source_name=doc["source_name"],
            is_pdf=doc.get("is_pdf", True)
        )
        total += count

    print(f"=== SELESAI SEMUA. Total {total} chunks di-ingest. ===")


if __name__ == "__main__":
    documents = [
        {"path": "templates/documents/JUKNIS_KALTIM_TUNTAS.pdf", "source_name": "kaltim_tuntas"},
        {"path": "templates/documents/PEDOMAN-BU-MAPRES-DISABILITAS_FINAL.pdf", "source_name": "beasiswa_unggulan"},
    ]
    ingest_all(documents)
