"""
Tool: search_knowledge — dipanggil LLM saat butuh informasi dari
basis pengetahuan Juknis beasiswa. Parameter 'program' WAJIB diisi
LLM berdasarkan nama program yang disebutkan user dalam percakapan.
"""

from typing import Literal
from livekit.agents import function_tool, RunContext

from app.rag.retriever import retrieve, format_context


@function_tool()
async def search_knowledge(
    context: RunContext,
    query: str,
    program: Literal["kaltim_tuntas", "beasiswa_unggulan"],
) -> str:
    """
    Cari informasi dari basis pengetahuan Juknis program beasiswa.
    Gunakan tool ini setiap kali user bertanya soal syarat, prosedur,
    dokumen yang dibutuhkan, atau ketentuan lain terkait beasiswa.

    Args:
        query: pertanyaan atau topik spesifik yang ingin dicari,
            tulis ulang dalam kalimat pencarian yang jelas
            (misal: "syarat dokumen untuk mahasiswa baru").
        program: program beasiswa yang dimaksud user. WAJIB diisi
            sesuai yang disebutkan user — "kaltim_tuntas" untuk
            Beasiswa Kaltim Tuntas, "beasiswa_unggulan" untuk
            Beasiswa Unggulan. Jika user belum menyebutkan program
            secara eksplisit, tanyakan dulu ke user sebelum memanggil
            tool ini.
    """
    results = retrieve(query=query, program=program, top_k=3)
    return format_context(results)