import json
import logging
import os
import re
from typing import Any
from livekit.agents import function_tool, RunContext

from app.agent.tools.document_engine import detect_template_fields, generate_document
from app.storage_service import upload_document
from app.voice_context import conversation_id_from_room

logger = logging.getLogger("andora.voice")

TEMPLATE_FILES = {
    "surat_pernyataan_5_poin": "templates/template_surat_5_point_andora_kaltim_tuntas.docx",
    "surat_pernyataan_pendaftar_beasiswa_unggulan": "templates/template-surat-pernyatan-pendaftar-bu.docx",
    "surat_pernyataan_disabilitas": "templates/template-surat-pernyataan-disabilitas.docx",
}


def resolve_template(nama_dokumen: str) -> tuple[str | None, str | None]:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", str(nama_dokumen).lower()).strip("_")
    if clean in TEMPLATE_FILES:
        return clean, TEMPLATE_FILES[clean]

    if "5" in clean or "lima" in clean or "kaltim" in clean:
        return "surat_pernyataan_5_poin", TEMPLATE_FILES["surat_pernyataan_5_poin"]
    if "disabilitas" in clean:
        return "surat_pernyataan_disabilitas", TEMPLATE_FILES["surat_pernyataan_disabilitas"]
    if "unggulan" in clean or "pendaftar" in clean:
        return "surat_pernyataan_pendaftar_beasiswa_unggulan", TEMPLATE_FILES["surat_pernyataan_pendaftar_beasiswa_unggulan"]

    return None, None


def get_conversation_identifier(room_name: str | None) -> str:
    if not room_name:
        return "lokal"
    try:
        return conversation_id_from_room(room_name)
    except Exception:
        return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(room_name))


def _generated_documents(context: RunContext) -> dict:
    userdata = getattr(context, "userdata", None)
    if userdata is None:
        return {}
    if not hasattr(userdata, "generated_documents"):
        userdata.generated_documents = {}
    return userdata.generated_documents


@function_tool()
async def siapkan_pengisian_dokumen(context: RunContext, nama_dokumen: str) -> str:
    """
    Panggil tool ini PERTAMA KALI saat user setuju untuk dibuatkan dokumen.
    Tool ini akan mengecek template dan memberitahumu (AI) data apa saja yang
    perlu ditanyakan ke user.

    Args:
        nama_dokumen: Nama dokumen, misal: "surat_pernyataan_5_poin".
    """
    logger.info(f"==> Tool siapkan_pengisian_dokumen dipanggil! nama_dokumen='{nama_dokumen}'")
    canonical_name, template_path = resolve_template(nama_dokumen)

    if not template_path or not os.path.exists(template_path):
        return (
            f"Maaf, template untuk '{nama_dokumen}' belum tersedia di server. "
            "TUGAS AI: Mohon maaf ke user dan bilang format ini belum bisa diotomatisasi."
        )

    fields = [
        "nama_lengkap",
        "nik",
        "tempat_tanggal_lahir",
        "univ",
        "fakultas",
        "jurusan",
        "jenjang",
        "semester",
        "alamat_asli",
        "alamat_sekarang",
        "nim",
    ]
    return f"""Sistem menemukan template '{canonical_name}'.
DAFTAR PERTANYAAN WAJIB:
Tanyakan ke user satu per satu sesuai urutan berikut:
1. Nama lengkap
2. NIK
3. Tempat dan tanggal lahir
4. Nama universitas
5. Fakultas
6. Jurusan
7. Jenjang (D3/D4/S1)
8. Semester
9. Alamat asli
10. Alamat domisili saat ini
11. NIM

PANDUAN PENTING UNTUK ANDORA:
- Tanyakan HANYA SATU pertanyaan dalam satu giliran.
- Jangan pernah beralasan 'kendala teknis' atau 'sedang memproses'.
- Begitu data ke-11 (NIM atau data terakhir) terjawab, Anda WAJIB langsung memanggil function tool `eksekusi_cetak_dokumen` dengan parameter:
  - nama_dokumen: "{canonical_name}"
  - data_isian: dictionary berisi seluruh jawaban user di atas.
- Jangan menunggu user bertanya lagi! Panggil tool tersebut saat itu juga!"""


@function_tool()
async def eksekusi_cetak_dokumen(
    context: RunContext,
    nama_dokumen: str = "surat_pernyataan_5_poin",
    data_isian: dict[str, str] = {},
) -> str:
    """
    Panggil tool ini setelah semua data yang diminta terkumpul untuk mencetak dokumen Word.

    Args:
        nama_dokumen: Nama dokumen, misal: "surat_pernyataan_5_poin".
        data_isian: Objek dictionary berisi pasangan key field dan value jawaban user.
            Contoh: {"nama_lengkap": "Ghani", "nik": "123", "nim": "456", "univ": "UGM"}
    """
    print(f"\n[TOOL CALL] eksekusi_cetak_dokumen: nama_dokumen='{nama_dokumen}', data_isian={data_isian}")
    logger.info(f"==> Tool eksekusi_cetak_dokumen dipanggil! nama_dokumen='{nama_dokumen}' | data={data_isian}")
    canonical_name, template_path = resolve_template(nama_dokumen)
    print(f"[TOOL INFO] canonical_name='{canonical_name}', template_path='{template_path}'")

    if not template_path or not os.path.exists(template_path):
        err_msg = f"Error: Template untuk '{nama_dokumen}' tidak ditemukan di server."
        print(f"[TOOL ERROR] {err_msg}")
        return err_msg

    try:
        data_dict = data_isian if isinstance(data_isian, dict) else {}

        room_name = context.room.name if (context.room and context.room.name) else None
        conv_id = get_conversation_identifier(room_name)
        file_name = f"{canonical_name}_{conv_id}.docx"

        os.makedirs("output_dokumen", exist_ok=True)
        output_path = os.path.join("output_dokumen", file_name)
        print(f"[TOOL STEP 1] Rendering template ke {output_path}...")

        # 1. Cetak dokumen ke server lokal
        hasil_generate = generate_document(
            template_path=template_path,
            output_path=output_path,
            data=data_dict,
        )
        print(f"[TOOL STEP 1 RESULT] {hasil_generate}")

        # 2. Upload file ke Supabase dan dapatkan URL public-nya
        print(f"[TOOL STEP 2] Mengunggah {output_path} ke Supabase Storage...")
        public_url = upload_document(output_path)
        print(f"[TOOL STEP 2 RESULT] Upload berhasil! Public URL: {public_url}")

        # 3. Simpan path lokal & URL ke memori backend (userdata)
        _generated_documents(context)[canonical_name] = {
            "local_path": output_path,
            "public_url": public_url,
            "file_name": file_name,
        }

        # 4. Lempar data (URL) langsung ke Frontend via Data Channel
        download_endpoint = f"/api/documents/download/{file_name}"
        if context.room and hasattr(context.room, "local_participant") and context.room.local_participant:
            payload = {
                "event": "DOCUMENT_READY",
                "nama_dokumen": canonical_name,
                "file_name": file_name,
                "url": public_url,
                "download_url": download_endpoint,
            }
            try:
                print(f"[TOOL STEP 4] Mengirim event DOCUMENT_READY via Data Channel...")
                await context.room.local_participant.publish_data(
                    json.dumps(payload),
                    reliable=True
                )
                print(f"[TOOL STEP 4 RESULT] Event DOCUMENT_READY terkirim ke frontend!")
            except Exception as pe:
                print(f"[TOOL STEP 4 WARNING] Gagal publish_data: {pe}")
                logger.warning(f"Gagal publish_data ke room data channel: {pe}")

        # 5. Return instruksi akhir ke AI
        print(f"[TOOL SUCCESS] Seluruh proses cetak dokumen selesai sempurna!\n")
        logger.info(f"==> eksekusi_cetak_dokumen SUKSES! file='{file_name}' public_url='{public_url}' download_endpoint='{download_endpoint}'")
        return (
            f"Laporan sistem: {hasil_generate}\n\n"
            f"TUGAS AI: Beritahu user dengan nada ramah bahwa dokumen '{canonical_name}' "
            f"sudah selesai dibuat. Arahkan user untuk mengklik tombol 'Download' yang "
            f"baru saja muncul di layar mereka. JANGAN pernah membacakan link URL-nya. "
            f"Terakhir, tanyakan apakah user ingin dokumen ini dikirimkan "
            f"sekarang ke email atau WhatsApp mereka."
        )

    except Exception as e:
        print(f"\n[TOOL EXCEPTION] Gagal saat mencetak dokumen '{nama_dokumen}': {e}")
        import traceback
        traceback.print_exc()
        logger.exception(f"Gagal mencetak dokumen '{nama_dokumen}': {e}")
        return f"Gagal mencetak dokumen: {str(e)}"
