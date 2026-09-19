import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import Any
from livekit.agents import function_tool, RunContext, get_job_context

from app.agent.tools.document_engine import detect_template_fields, generate_document
from app.storage_service import upload_document
from app.voice_context import conversation_id_from_room

logger = logging.getLogger("andora.voice")


def _get_livekit_room(context: RunContext):
    """Ambil rtc.Room aktif dari session/job context.

    RunContext tidak punya atribut `room`, akses yang benar lewat
    session.room_io.room dengan fallback ke get_job_context().room.
    """
    session = getattr(context, "session", None)
    room_io = getattr(session, "room_io", None) if session is not None else None
    room = getattr(room_io, "room", None) if room_io is not None else None
    if room is not None:
        return room
    legacy_room = getattr(context, "room", None)
    if legacy_room is not None:
        return legacy_room
    try:
        job_ctx = get_job_context(required=False)
    except Exception:
        job_ctx = None
    if job_ctx is not None:
        return getattr(job_ctx, "room", None)
    return None

FIELD_LABELS = {
    "nama_lengkap": "Nama lengkap",
    "name": "Nama lengkap",
    "nama": "Nama lengkap",
    "nik": "NIK",
    "tempat_tanggal_lahir": "Tempat dan tanggal lahir",
    "tempat_lahir": "Tempat lahir",
    "tanggal_lahir": "Tanggal lahir",
    "birth_place": "Tempat lahir",
    "birth_date": "Tanggal lahir",
    "tempat_dan_tanggal": "Tempat dan tanggal lahir",
    "univ": "Nama universitas",
    "universitas": "Nama universitas",
    "university": "Nama universitas",
    "fakultas": "Fakultas",
    "jurusan": "Jurusan",
    "jenjang": "Jenjang (D3/D4/S1)",
    "education_level": "Jenjang pendidikan",
    "semester": "Semester",
    "alamat_asli": "Alamat asli",
    "alamat": "Alamat",
    "alamat_sekarang": "Alamat domisili saat ini",
    "alamat_domisili": "Alamat domisili saat ini",
    "country_province": "Kabupaten/provinsi",
    "nim": "NIM",
    "job_institution": "Pekerjaan/institusi",
    "jenis_disabilitas": "Jenis disabilitas",
    "date": "Tanggal surat",
}

FIELD_ALIASES = {
    "nama_lengkap": {"nama_lengkap", "name", "nama"},
    "name": {"nama_lengkap", "name", "nama"},
    "nama": {"nama_lengkap", "name", "nama"},
    "nik": {"nik", "nomor_induk_kependudukan", "no_ktp"},
    "tempat_tanggal_lahir": {"tempat_tanggal_lahir", "tempat_dan_tanggal"},
    "tempat_lahir": {"tempat_lahir", "birth_place"},
    "tanggal_lahir": {"tanggal_lahir", "birth_date"},
    "birth_place": {"tempat_lahir", "birth_place"},
    "birth_date": {"tanggal_lahir", "birth_date"},
    "tempat_dan_tanggal": {"tempat_tanggal_lahir", "tempat_dan_tanggal"},
    "univ": {"univ", "universitas", "university"},
    "universitas": {"univ", "universitas", "university"},
    "university": {"univ", "universitas", "university"},
    "jenjang": {"jenjang", "education_level"},
    "education_level": {"jenjang", "education_level"},
    "alamat_asli": {"alamat_asli", "alamat"},
    "alamat": {"alamat_asli", "alamat"},
    "alamat_sekarang": {"alamat_sekarang", "alamat_domisili"},
    "alamat_domisili": {"alamat_sekarang", "alamat_domisili"},
}


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")


def _normalize_document_data(template_fields: list[str], data: Any) -> dict[str, str]:
    """Petakan isian model ke field template yang sebenarnya.

    Model realtime kadang mengirim alias (mis. `universitas` untuk `univ`
    atau `tempat_lahir`/`tanggal_lahir` terpisah). Normalisasi ini
    menggabungkan alias tersebut agar render tidak kehilangan data.
    """
    raw: dict[str, Any] = {}
    if isinstance(data, dict):
        raw = data
    elif isinstance(data, str):
        try:
            parsed = json.loads(data)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            raw = parsed

    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            cleaned[_normalize_key(key)] = text

    normalized: dict[str, str] = {}
    for field in template_fields:
        norm_field = _normalize_key(field)
        candidates = {norm_field}
        candidates.update(_normalize_key(a) for a in FIELD_ALIASES.get(norm_field, set()))
        for candidate in candidates:
            if candidate in cleaned:
                normalized[field] = cleaned[candidate]
                break

    if "tempat_tanggal_lahir" in template_fields and "tempat_tanggal_lahir" not in normalized:
        tempat = cleaned.get("tempat_lahir", "")
        tanggal = cleaned.get("tanggal_lahir", "")
        combined = ", ".join(p for p in [tempat, tanggal] if p)
        if combined:
            normalized["tempat_tanggal_lahir"] = combined
    if "tempat_dan_tanggal" in template_fields and "tempat_dan_tanggal" not in normalized:
        tempat = cleaned.get("tempat_lahir", "")
        tanggal = cleaned.get("tanggal_lahir", "")
        combined = ", ".join(p for p in [tempat, tanggal] if p)
        if combined:
            normalized["tempat_dan_tanggal"] = combined

    return normalized


AUTO_FILL_FIELDS = {"date"}


def _label_for_field(field: str) -> str:
    if field in FIELD_LABELS:
        return FIELD_LABELS[field]
    return _normalize_key(field).replace("_", " ")


def _auto_fill_missing(template_fields: list[str], normalized: dict[str, str]) -> dict[str, str]:
    """Isi otomatis field sistem seperti tanggal surat hari ini."""
    filled = dict(normalized)
    today = datetime.now().strftime("%d %B %Y")
    for field in template_fields:
        if field in filled:
            continue
        if _normalize_key(field) in AUTO_FILL_FIELDS:
            filled[field] = today
    return filled


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
    if isinstance(userdata, dict):
        return userdata.setdefault("generated_documents", {})
    if not hasattr(userdata, "generated_documents") or getattr(userdata, "generated_documents") is None:
        userdata.generated_documents = {}
    store = getattr(userdata, "generated_documents")
    if isinstance(store, dict):
        return store
    return {}


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

    try:
        fields = detect_template_fields(template_path)
    except Exception as exc:
        logger.exception(f"Gagal membaca field template '{canonical_name}': {exc}")
        return (
            f"Maaf, template '{canonical_name}' tidak bisa dibaca server. "
            "TUGAS AI: Minta maaf ke user dan sarankan coba lagi nanti."
        )
    if not fields:
        return (
            f"Maaf, template '{canonical_name}' tidak punya field isian. "
            "TUGAS AI: Beritahu user bahwa dokumen ini belum bisa dibuat otomatis."
        )

    numbered = "\n".join(
        f"{i}. {_label_for_field(f)} (key: `{f}`)" for i, f in enumerate(fields, start=1)
    )
    return f"""Sistem menemukan template '{canonical_name}'.
DAFTAR PERTANYAAN WAJIB ({len(fields)} FIELD):
{numbered}

PANDUAN PENTING UNTUK ANDORA:
- Tanyakan HANYA SATU pertanyaan dalam satu giliran, sesuai urutan di atas.
- Jangan menambah, mengurangi, atau menebak field di luar daftar.
- Jika user bertanya "apa saja yang dibutuhkan?", bacakan daftar di atas secara ringkas lalu mulai wawancara.
- Begitu field terakhir ({_label_for_field(fields[-1])}) terjawab, Anda WAJIB langsung memanggil function tool `eksekusi_cetak_dokumen` dengan parameter:
  - nama_dokumen: "{canonical_name}"
  - data_isian: dictionary berisi SELURUH jawaban user memakai key persis seperti field template di atas.
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

    if not canonical_name or not template_path or not os.path.exists(template_path):
        err_msg = f"Error: Template untuk '{nama_dokumen}' tidak ditemukan di server."
        print(f"[TOOL ERROR] {err_msg}")
        return err_msg

    try:
        template_fields = detect_template_fields(template_path)
    except Exception as exc:
        logger.exception(f"Gagal membaca field template '{canonical_name}': {exc}")
        return f"Gagal membaca template '{canonical_name}': {exc}"

    data_dict = _normalize_document_data(template_fields, data_isian)
    data_dict = _auto_fill_missing(template_fields, data_dict)
    missing = [f for f in template_fields if f not in data_dict]
    if missing:
        labels = ", ".join(_label_for_field(f) for f in missing)
        print(f"[TOOL ERROR] Data belum lengkap, kurang: {missing}")
        return (
            f"Data belum lengkap untuk '{canonical_name}'. Masih kurang: {labels}. "
            "TUGAS AI: Tanyakan SATU PER SATU data yang kurang tersebut, "
            "lalu panggil lagi eksekusi_cetak_dokumen dengan data lengkap."
        )

    try:
        room = _get_livekit_room(context)
        room_name = getattr(room, "name", None) if room is not None else None
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
        if hasil_generate.startswith("Gagal") or not os.path.exists(output_path):
            print(f"[TOOL ERROR] {hasil_generate}")
            return (
                f"{hasil_generate} "
                "TUGAS AI: Minta maaf ke user bahwa dokumen gagal dibuat, "
                "jangan bilang dokumen sudah selesai."
            )

        # 2. Upload file ke Supabase dan dapatkan URL public-nya.
        # File lokal tetap dianggap sukses walau upload gagal, supaya
        # user tetap bisa unduh via endpoint backend.
        print(f"[TOOL STEP 2] Mengunggah {output_path} ke Supabase Storage...")
        try:
            public_url = await asyncio.to_thread(upload_document, output_path)
        except Exception as exc:
            public_url = ""
            print(f"[TOOL STEP 2 WARNING] Upload Supabase gagal: {exc}")
            logger.warning(f"Upload Supabase gagal untuk {output_path}: {exc}")
        else:
            print(f"[TOOL STEP 2 RESULT] Upload berhasil! Public URL: {public_url}")

        # 3. Simpan path lokal & URL ke memori backend (userdata)
        _generated_documents(context)[canonical_name] = {
            "local_path": output_path,
            "public_url": public_url,
            "file_name": file_name,
        }
        if nama_dokumen and nama_dokumen != canonical_name:
            _generated_documents(context)[nama_dokumen] = {
                "local_path": output_path,
                "public_url": public_url,
                "file_name": file_name,
            }

        # 4. Lempar data (URL) langsung ke Frontend via Data Channel
        download_endpoint = f"/api/documents/download/{file_name}"
        local_participant = getattr(room, "local_participant", None) if room is not None else None
        if local_participant:
            payload = {
                "event": "DOCUMENT_READY",
                "nama_dokumen": canonical_name,
                "file_name": file_name,
                "url": public_url,
                "download_url": download_endpoint,
            }
            try:
                print(f"[TOOL STEP 4] Mengirim event DOCUMENT_READY via Data Channel...")
                await local_participant.publish_data(
                    json.dumps(payload),
                    reliable=True
                )
                print(f"[TOOL STEP 4 RESULT] Event DOCUMENT_READY terkirim ke frontend!")
            except Exception as pe:
                print(f"[TOOL STEP 4 WARNING] Gagal publish_data: {pe}")
                logger.warning(f"Gagal publish_data ke room data channel: {pe}")
        else:
            print("[TOOL STEP 4 WARNING] Room/local_participant tidak tersedia, event DOCUMENT_READY dilewati.")
            logger.warning("Room/local_participant tidak tersedia, event DOCUMENT_READY dilewati.")

        # 5. Return instruksi akhir ke AI
        print(f"[TOOL SUCCESS] Seluruh proses cetak dokumen selesai sempurna!\n")
        logger.info(f"==> eksekusi_cetak_dokumen SUKSES! file='{file_name}' public_url='{public_url}' download_endpoint='{download_endpoint}'")
        upload_note = (
            ""
            if public_url
            else " Catatan: upload cloud gagal, tapi tombol unduh backend tetap tersedia."
        )
        return (
            f"Laporan sistem: {hasil_generate}{upload_note}\n\n"
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
