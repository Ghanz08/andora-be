from typing import Literal
from livekit.agents import function_tool, RunContext
from app.rag.retriever import retrieve, format_context

# 1. Kelompokkan template berdasarkan program beasiswanya
TEMPLATE_TERSEDIA = {
    "kaltim_tuntas": [
        "surat_pernyataan_5_poin (Catatan untuk AI: Dokumen tunggal ini sudah merangkum/mencakup ke-5 syarat pernyataan yang disebutkan di dalam Juknis. Tawarkan ini untuk menyelesaikan semua syarat pernyataan tersebut sekaligus)",

    ],
    "beasiswa_unggulan": [
        "surat_pernyataan_disabilitas", 
        "surat_pernyataan_pendaftar_beasiswa_unggulan",
    ]
}

@function_tool()
async def search_knowledge(
    context: RunContext,
    query: str,
    program: Literal["kaltim_tuntas", "beasiswa_unggulan"],
) -> str:
    """Cari informasi persyaratan dan petunjuk teknis beasiswa di basis pengetahuan."""
    
    # 2. Tarik konteks Juknis asli
    results = retrieve(query=query, program=program, top_k=3)
    konteks_rag = format_context(results)
    
    # 3. Ambil daftar template HANYA untuk program yang sedang ditanyakan
    template_program_ini = TEMPLATE_TERSEDIA.get(program, [])
    
    # 4. Jika ada template untuk program ini, sisipkan pesan rahasia
    if template_program_ini:
        pesan_sistem = (
            f"\n\n--- INFO INTERNAL SISTEM UNTUK AI (JANGAN DIBACAKAN MENTAH-MENTAH) ---\n"
            f"Untuk program {program}, kamu memiliki kemampuan mencetak dokumen berikut: "
            f"[{', '.join(template_program_ini)}].\n"
            f"Jika hasil pencarian Juknis di atas mewajibkan salah satu dokumen ini, "
            f"kamu WAJIB proaktif menawarkan bantuan ke user untuk membuatkannya sekarang.\n"
            f"Jika dokumen yang diminta tidak ada di daftar atas, jangan tawarkan bantuan."
        )
        return konteks_rag + pesan_sistem
    
    # 5. Jika tidak ada template sama sekali untuk program tersebut, 
    # kembalikan teks RAG murni tanpa pesan rahasia.
    return konteks_rag