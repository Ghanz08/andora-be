import io
import os
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import RedirectResponse, Response

from app.storage_service import download_document_bytes, get_document_url

router = APIRouter()

UPLOAD_DIR = "temp_uploads"
ALLOWED_EXTENSIONS = {".pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.get("/api/documents/download/{file_name}")
async def download_generated_document(file_name: str, redirect: bool = False):
    """
    Endpoint backend untuk mengakses/mendownload file dokumen yang dihasilkan.
    Jika ?redirect=true, akan otomatis redirect ke public URL Supabase Storage.
    Secara default, mengalirkan bytes file .docx langsung sebagai attachment download.
    """
    if not file_name.endswith(".docx") and not file_name.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Tipe file tidak valid")

    if redirect:
        url = get_document_url(file_name)
        return RedirectResponse(url=url)

    try:
        content = download_document_bytes(file_name)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}"'
            },
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Dokumen tidak ditemukan: {str(e)}")


@router.post("/api/documents/upload")
async def upload_document(
    room_name: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Terima file dokumen dari FE, simpan sebagai {room_name}_latest.pdf
    di temp_uploads/, supaya nanti bisa dibaca oleh tool
    read_uploaded_document di sesi voice yang sama.
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Format file tidak didukung. Hanya PDF yang diterima."
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Ukuran file terlalu besar (maks 10MB).")

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # nama file SELALU "{room_name}_latest.pdf" -> otomatis overwrite
    # kalau user upload dokumen baru di sesi yang sama
    target_path = os.path.join(UPLOAD_DIR, f"{room_name}_latest.pdf")

    with open(target_path, "wb") as f:
        f.write(contents)

    return {
        "status": "success",
        "message": "Dokumen berhasil diupload.",
        "room_name": room_name,
    }