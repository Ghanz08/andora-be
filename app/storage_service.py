import os
from app.integrations.supabase_client import get_supabase_client

supabase = get_supabase_client()

BUCKET_NAME = "generated-documents"  # buat dulu bucket ini di Supabase Storage dashboard


def upload_document(file_path: str) -> str:
    """
    Upload file dokumen ke Supabase Storage, return public URL-nya.
    """
    file_name = os.path.basename(file_path)
    storage_path = f"documents/{file_name}"

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # upsert=True biar bisa overwrite kalau file dengan nama sama udah ada
    supabase.storage.from_(BUCKET_NAME).upload(
        path=storage_path,
        file=file_bytes,
        file_options={
            "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "upsert": "true",
        },
    )

    public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)
    return public_url