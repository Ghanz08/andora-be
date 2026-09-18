import json
import os
from livekit.agents import function_tool, RunContext
from livekit import rtc # Tambahan untuk Data Channel

# Pastikan import ini sesuai dengan struktur folder proyekmu
from app.agent.tools.document_engine import generate_document
from app.storage_service import upload_document

from app.agent.tools.document_engine import detect_template_fields, generate_document
from app.storage_service import upload_document

TEMPLATE_FILES = {
    "surat_pernyataan_5_poin": "templates/template_surat_5_point_andora_kaltim_tuntas.docx",
    "surat_pernyataan_pendaftar_beasiswa_unggulan": "templates/template-surat-pernyatan-pendaftar-bu.docx",
    "surat_pernyataan_disabilitas": "templates/template-surat-pernyataan-disabilitas.docx",
}


@function_tool()
async def siapkan_pengisian_dokumen(context: RunContext, nama_dokumen: str) -> str:
    """
    Panggil tool ini PERTAMA KALI saat user setuju untuk dibuatkan dokumen.
    Tool ini akan mengecek template dan memberitahumu (AI) data apa saja yang
    perlu ditanyakan ke user.

    Args:
        nama_dokumen: Nama dokumen dalam format snake_case persis sesuai key
            yang tersedia, misal: "surat_pernyataan_5_poin".
    """
    template_path = TEMPLATE_FILES.get(nama_dokumen)

    if not template_path or not os.path.exists(template_path):
        return (
            f"Maaf, template untuk '{nama_dokumen}' belum tersedia di server. "
            "TUGAS AI: Mohon maaf ke user dan bilang format ini belum bisa diotomatisasi."
        )

    try:
        fields_dibutuhkan = detect_template_fields(template_path)
        return (
            f"Sistem menemukan template '{nama_dokumen}'. \n"
            f"Data yang WAJIB diisi adalah: {fields_dibutuhkan}.\n\n"
            f"TUGAS AI MULAI SEKARANG: Wawancarai user untuk mendapatkan data tersebut. "
            f"Tanyakan SATU PER SATU secara natural, jangan sebutkan semuanya sekaligus. "
            f"Setelah SEMUA data terkumpul, barulah panggil tool 'eksekusi_cetak_dokumen'."
        )
    except Exception as e:
        return f"Sistem error saat membaca template: {str(e)}"


@function_tool()
async def eksekusi_cetak_dokumen(
    context: RunContext,
    nama_dokumen: str,
    data_isian_json: str,
) -> str:
    """
    Panggil tool ini HANYA JIKA semua data yang diminta dari persiapan sudah
    terkumpul. Ini akan benar-benar mencetak dokumen Word.

    Args:
        nama_dokumen: Nama dokumen dalam format snake_case, misal:
            "surat_pernyataan_5_poin".
        data_isian_json: String berformat JSON murni berisi key (sesuai field)
            dan value (jawaban user). Contoh: '{"nama_lengkap": "Budi", "nik": "123456"}'
    """
    template_path = TEMPLATE_FILES.get(nama_dokumen)

    if not template_path:
        return "Error: Template tidak ditemukan."

    try:
        data_dict = json.loads(data_isian_json)

        room_name = context.room.name if context.room else "lokal_user"
        safe_name = nama_dokumen.replace(" ", "_").lower()

        os.makedirs("output_dokumen", exist_ok=True)
        output_path = f"output_dokumen/{safe_name}_{room_name}.docx"

        # 1. Cetak dokumen ke server lokal
        hasil_generate = generate_document(
            template_path=template_path,
            output_path=output_path,
            data=data_dict,
        )

        # 2. Upload file ke Supabase dan dapatkan URL public-nya
        public_url = upload_document(output_path)

        # 3. Simpan path lokal & URL ke memori backend (userdata)
        # Berguna untuk tool lain nanti (misal: kirim_dokumen ke email/WA)
        if hasattr(context, "userdata") and context.userdata is not None:
            context.userdata.generated_documents[nama_dokumen] = {
                "local_path": output_path,
                "public_url": public_url
            }

        # 4. Lempar data (URL) langsung ke Frontend via Data Channel
        if context.room:
            payload = {
                "event": "DOCUMENT_READY",
                "nama_dokumen": nama_dokumen,
                "url": public_url
            }
            # Kirim sinyal ke FE agar memunculkan tombol Download
            await context.room.local_participant.publish_data(
                json.dumps(payload).encode("utf-8"),
                reliable=True
            )

        # 5. Return instruksi akhir ke AI
        return (
            f"Laporan sistem: {hasil_generate}\n\n"
            f"TUGAS AI: Beritahu user dengan nada ramah bahwa dokumen '{nama_dokumen}' "
            f"sudah selesai dibuat. Arahkan user untuk mengklik tombol 'Download' yang "
            f"baru saja muncul di layar mereka. JANGAN pernah membacakan link URL-nya. "
            f"Terakhir, tanyakan apakah user ingin dokumen ini dikirimkan "
            f"sekarang ke email atau WhatsApp mereka."
        )

    except json.JSONDecodeError:
        return (
            "Gagal mencetak: Format 'data_isian_json' yang kamu (AI) kirim tidak valid. "
            "Pastikan formatnya JSON murni. Coba panggil tool ini lagi."
        )
    except Exception as e:
        return f"Gagal mencetak dokumen: {str(e)}"