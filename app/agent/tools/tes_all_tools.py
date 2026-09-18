"""
Test script manual — jalanin semua tools secara berurutan TANPA perlu
LiveKit voice session beneran. Pakai FakeContext buat simulasiin
RunContext (userdata + room) yang biasanya disediain LiveKit Agents.

Cara pakai:
    python3 test_all_tools.py

CATATAN: sesuaikan import path di bawah sesuai struktur project kamu,
dan pastikan .env udah keisi (OPENAI_API_KEY, SUPABASE_URL, SMTP_*, dll)
sebelum run.
"""

import asyncio
from dataclasses import dataclass, field


# ==========================================
# FAKE CONTEXT — simulasi RunContext LiveKit
# ==========================================

@dataclass
class SessionData:
    generated_documents: dict[str, str] = field(default_factory=dict)


class FakeLocalParticipant:
    async def publish_data(self, data: bytes):
        print(f"[FAKE publish_data] Data channel terkirim: {data.decode()}")


class FakeRoom:
    name = "test_room_001"
    local_participant = FakeLocalParticipant()


class FakeContext:
    def __init__(self):
        self.userdata = SessionData()
        self.room = FakeRoom()


# ==========================================
# IMPORT TOOLS — sesuaikan path-nya
# ==========================================

from app.agent.tools.search_knowledge import search_knowledge
from app.agent.tools.read_document import read_uploaded_document, process_document_query
from app.agent.tools.document_tools import siapkan_pengisian_dokumen, eksekusi_cetak_dokumen
from app.agent.tools.kirim_dokumen import kirim_dokumen


# ==========================================
# HELPER buat print rapi
# ==========================================

def print_result(step_name: str, result: str):
    print(f"\n{'=' * 60}")
    print(f"STEP: {step_name}")
    print('=' * 60)
    print(result)


# ==========================================
# SKENARIO END-TO-END
# ==========================================

async def main():
    ctx = FakeContext()

    # --- STEP 1: search_knowledge (RAG) ---
    # Ganti query & program sesuai dokumen yang udah kamu ingest
    hasil_1 = await search_knowledge(
        ctx,
        query="apa syarat dokumen yang dibutuhkan mahasiswa?",
        program="kaltim_tuntas",
    )
    print_result("1. search_knowledge", hasil_1)

    # --- STEP 2: read_uploaded_document ---
    # NOTE: tool ini baca dari path temp_uploads/{room_name}_latest.pdf
    # Siapkan dulu file dummy di path itu kalau mau test jalur sukses.
    # Kalau file belum ada, ini bakal nunjukin jalur error-handling-nya.
    hasil_2 = await read_uploaded_document(
        ctx,
        pertanyaan_spesifik="Kapan pendaftaran ditutup?",
    )
    print_result("2. read_uploaded_document", hasil_2)

    # --- STEP 3: siapkan_pengisian_dokumen ---
    # Ganti nama_dokumen sesuai key yang ada di TEMPLATE_FILES
    hasil_3 = await siapkan_pengisian_dokumen(
        ctx,
        nama_dokumen="surat_pernyataan_5_poin",
    )
    print_result("3. siapkan_pengisian_dokumen", hasil_3)

    # --- STEP 4: eksekusi_cetak_dokumen ---
    # Data dummy — sesuaikan field-nya dengan yang muncul di hasil step 3
    data_dummy = {
        "nama_lengkap": "Budi Santoso",
        "nik": "6472011234560001",
        "univ": "Universitas Mulawarman",
        "nim": "2009106011",
        "fakultas": "Ilmu Komputer dan Teknologi Informasi",
        "jurusan": "Informatika",
        "jenjang": "S1",
        "semester": "6",
    }
    import json
    hasil_4 = await eksekusi_cetak_dokumen(
        ctx,
        nama_dokumen="surat_pernyataan_5_poin",
        data_isian_json=json.dumps(data_dummy),
    )
    print_result("4. eksekusi_cetak_dokumen", hasil_4)

    # Cek apakah userdata udah keisi path dokumen (ini yang penting divalidasi)
    print(f"\n[CHECK] userdata.generated_documents = {ctx.userdata.generated_documents}")

    # --- STEP 5a: kirim_dokumen via EMAIL ---
    # Ganti ke email asli kamu buat test beneran (atau skip kalau SMTP belum di-setup)
    hasil_5a = await kirim_dokumen(
        ctx,
        nama_dokumen="surat_pernyataan_5_poin",
        channel="email",
        tujuan="test@example.com",
    )
    print_result("5a. kirim_dokumen (email)", hasil_5a)

    # --- STEP 5b: kirim_dokumen via WHATSAPP ---
    # Ini gak beneran kirim, cuma test payload data channel-nya kekirim (lihat FakeLocalParticipant)
    hasil_5b = await kirim_dokumen(
        ctx,
        nama_dokumen="surat_pernyataan_5_poin",
        channel="whatsapp",
        tujuan="628123456789",
    )
    print_result("5b. kirim_dokumen (whatsapp)", hasil_5b)

    print(f"\n{'=' * 60}")
    print("SEMUA STEP SELESAI")
    print('=' * 60)


if __name__ == "__main__":
    asyncio.run(main())