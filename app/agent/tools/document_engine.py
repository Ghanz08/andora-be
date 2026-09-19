import os

def detect_template_fields(template_path: str) -> list[str]:
    """
    Membaca file Word dan mengembalikan daftar semua variabel {{ ... }} 
    yang harus diisi menggunakan fungsi bawaan docxtpl.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template tidak ditemukan: {template_path}")

    from docxtpl import DocxTemplate

    doc = DocxTemplate(template_path)
    
    # Gunakan fungsi bawaan docxtpl ini (langsung mengembalikan set variabel)
    fields = doc.get_undeclared_template_variables()
    
    return sorted(list(fields))

def generate_document(template_path: str, output_path: str, data: dict) -> str:
    """
    Mengisi template Word apapun menggunakan dictionary data.
    Key yang hilang diisi string kosong agar render tidak gagal.
    """
    if not os.path.exists(template_path):
        return f"Gagal: Template {template_path} tidak ditemukan."

    try:
        from docxtpl import DocxTemplate

        fields = detect_template_fields(template_path)
        safe_data = {k: "" for k in fields}
        if isinstance(data, dict):
            for key, value in data.items():
                safe_data[str(key)] = "" if value is None else str(value)

        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        doc = DocxTemplate(template_path)
        doc.render(safe_data)
        doc.save(output_path)
        if not os.path.exists(output_path):
            return f"Gagal: File output tidak terbentuk di {output_path}."
        return f"Sukses! Dokumen di-generate di {output_path}"
    except Exception as e:
        return f"Gagal memproses dokumen: {str(e)}"

# ==========================================
# BLOK TESTING MANUAL
# ==========================================
if __name__ == "__main__":
    # Asumsi kamu punya file ini dengan tag {{ nama }}, {{ nik }}, {{ tujuan }}
    # Buat file dummy .docx ini dulu di komputermu sebelum di-run!
    test_template = "templates/template_surat_5_point_andora_kaltim_tuntas.docx"
    test_output = "templates/output/surat_terisi.docx"
    
    # Pastikan folder ada
    os.makedirs("templates/dokumen", exist_ok=True)
    os.makedirs("output_dokumen", exist_ok=True)
    
    print("1. Mendeteksi field otomatis dari Word...")
    try:
        dibutuhkan = detect_template_fields(test_template)
        print(f"Field yang wajib diisi: {dibutuhkan}")
        
        print("\n2. Mengisi dokumen dengan data dinamis...")
        # Dictionary ini nantinya berasal dari hasil JSON yang dilempar LLM
        data_user = {
    "nama_lengkap": "Andi Darmawan",
    "tempat_tanggal_lahir": "Samarinda, 17 Agustus 2002",
    "alamat_sekarang": "Jl. M. Yamin No. 15, Samarinda",
    "alamat_asli": "Jl. Mulawarman No. 42, Tenggarong",
    "nik": "6472011234560001",
    "univ": "Universitas Mulawarman",
    "nim": "2009106011",
    "fakultas": "Ilmu Komputer dan Teknologi Informasi",
    "jurusan": "Informatika",
    "jenjang": "S1",
    "semester": "6"
}
        hasil = generate_document(test_template, test_output, data_user)
        print(hasil)
        
    except FileNotFoundError:
        print(f"Silakan buat file {test_template} di MS Word dengan tag {{ nama }} dsb untuk mencoba.")
