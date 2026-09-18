import os
import pdfplumber
from livekit.agents import function_tool, RunContext

# ==========================================
# 1. LOGIKA UTAMA (Independen & Bisa Dites)
# ==========================================
def extract_document_text(file_path: str) -> str:
    """Membaca isi file PDF."""
    if not os.path.exists(file_path):
        return "Maaf, sistem tidak dapat menemukan dokumen yang baru saja diunggah."
    
    if file_path.endswith('.pdf'):
        text = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            
            if not text.strip():
                return "Dokumen PDF kosong atau teksnya berupa gambar yang tidak bisa dibaca langsung."
            
            return text
        except Exception as e:
            return f"Terjadi kesalahan saat membaca PDF: {str(e)}"
    
    return "Maaf, format dokumen ini belum didukung. Sistem hanya menerima PDF."

def process_document_query(file_path: str, pertanyaan: str = "") -> str:
    """Memproses teks dan merakit prompt untuk LLM."""
    isi_dokumen = extract_document_text(file_path)
    
    # Jika ada error atau file tidak valid, langsung kembalikan pesan errornya
    if "Maaf" in isi_dokumen or "Terjadi kesalahan" in isi_dokumen:
        return isi_dokumen

    if pertanyaan:
        return (
            f"Isi dokumen:\n{isi_dokumen}\n\n"
            f"TUGAS AI: Jawab pertanyaan '{pertanyaan}' berdasarkan dokumen."
        )
    return (
        f"Isi dokumen:\n{isi_dokumen}\n\n"
        f"TUGAS AI: Bacakan rangkuman dokumen ini."
    )
# ==========================================
# 2. PEMBUNGKUS LIVEKIT (Untuk Agen Suara)
# ==========================================
@function_tool()
async def read_uploaded_document(
    context: RunContext,
    pertanyaan_spesifik: str = "",
) -> str:
    """
    Baca isi dokumen yang baru diunggah user.
    Args:
        pertanyaan_spesifik: Pertanyaan user terkait isi dokumen. Kosongkan jika hanya minta dibacakan.
    """
    room_name = context.room.name if context.room else "default_room"
    target_file = f"/home/naziri/Desktop/my_python/andora-be/temp_uploads/{room_name}_latest.pdf" 
    
    # AI memanggil fungsi independen di atas
    return process_document_query(target_file, pertanyaan_spesifik)

# ==========================================
# 3. BLOK TESTING MANUAL (Jalan tanpa LiveKit)
# ==========================================
if __name__ == "__main__":
    print("=== Memulai Tes Manual Tanpa LiveKit ===\n")
    
    # 1. Siapkan folder dan file dummy untuk tes
    os.makedirs("temp_uploads", exist_ok=True)
    test_file_path = "/home/naziri/Desktop/my_python/andora-be/templates/documents/tes_read_doc.pdf"
  
    # 2. Tes skenario pertama: User minta rangkuman (tanpa pertanyaan spesifik)
    print("Skenario 1: User bilang 'Tolong bacakan dokumennya'")
    hasil_1 = process_document_query(test_file_path)
    print(f"Hasil Prompt ke LLM:\n{hasil_1}\n")
    
    # 3. Tes skenario kedua: User nanya hal spesifik
    print("Skenario 2: User nanya 'Kapan pendaftaran ditutup?'")
    hasil_2 = process_document_query(test_file_path, pertanyaan="Kapan pendaftaran ditutup?")
    print(f"Hasil Prompt ke LLM:\n{hasil_2}\n")

    # Bersihkan file tes setelah selesai
    os.remove(test_file_path)
    print("=== Tes Selesai ===")