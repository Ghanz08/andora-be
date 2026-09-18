"""
Chunking module — extract teks dari PDF/txt dan pecah jadi chunk
yang siap di-embed untuk RAG.

Disesuaikan untuk struktur Juknis Kaltim Tuntas:
- Level 1 (heading utama): angka romawi + titik, misal "I. Pendahuluan"
- Level 2 (sub-heading): huruf kapital + titik, misal "A. Latar belakang"
- List bernomor (1. 2. 3.) dan bullet huruf kecil (a. b. c.) DIANGGAP
  sebagai isi konten, bukan heading baru.
"""

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    content: str
    metadata: dict


# Level 1: angka romawi di awal baris, diikuti titik, spasi, lalu judul
LEVEL1_PATTERN = re.compile(
    r'^(?P<num>[IVXLC]+)\.\s+(?P<title>[A-ZÀ-Ú][^\n]*)$',
    re.MULTILINE
)

# Level 2: SATU huruf kapital di awal baris, diikuti titik, spasi, lalu judul
# (beda dari list "a." "b." yang huruf kecil, dan beda dari "1." "2." yang angka)
LEVEL2_PATTERN = re.compile(
    r'^(?P<letter>[A-Z])\.\s+(?P<title>[A-ZÀ-Ú][^\n]*)$',
    re.MULTILINE
)


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract teks dari PDF pakai pdfplumber."""
    import pdfplumber
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    return full_text


def extract_text_from_txt(txt_path: str) -> str:
    """Fallback kalau sumbernya udah teks polos, bukan PDF."""
    with open(txt_path, "r", encoding="utf-8") as f:
        return f.read()


def roman_to_int(s: str) -> int:
    values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}
    total, prev = 0, 0
    for ch in reversed(s):
        v = values.get(ch, 0)
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total


def find_true_roman_chain(ints: list[int]) -> list[int]:
    """
    Cari rantai INDEX yang nilainya beneran konsekutif naik 1-1
    (1,2,3,4,...) dari kumpulan match yang ketangkep regex.
    Match yang 'nyelip' di tengah tapi gak nyambung urutannya
    dianggap false positive (kemungkinan besar itu sub-heading,
    bukan heading utama) dan di-skip.
    """
    best_chain = []
    for start in range(len(ints)):
        if ints[start] not in (1, 2):  # heading pertama wajar mulai dari I atau II
            continue
        chain = [start]
        expected = ints[start] + 1
        for i in range(start + 1, len(ints)):
            if ints[i] == expected:
                chain.append(i)
                expected += 1
        if len(chain) > len(best_chain):
            best_chain = chain
    return best_chain


def split_level1(text: str) -> list[dict]:
    """Pecah dokumen jadi section besar berdasarkan heading romawi."""
    all_matches = list(LEVEL1_PATTERN.finditer(text))
    ints = [roman_to_int(m.group('num')) for m in all_matches]

    chain_idx = find_true_roman_chain(ints)

    # minimal 3 heading berurutan biar dianggap struktur romawi asli
    if len(chain_idx) < 3:
        return [{"heading": "Dokumen Penuh", "content": text}]

    matches = [all_matches[i] for i in chain_idx]  # cuma yang beneran valid

    sections = []
    for i, match in enumerate(matches):
        heading = f"{match.group('num')}. {match.group('title')}".strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            sections.append({"heading": heading, "content": content})

    return sections


def split_level2(parent_heading: str, content: str) -> list[dict]:
    """
    Coba pecah lagi section level-1 berdasarkan sub-heading (A. B. C.).
    Kalau gak ada sub-heading, balikin section itu utuh sebagai 1 bagian.
    """
    matches = list(LEVEL2_PATTERN.finditer(content))

    if not matches:
        return [{"heading": parent_heading, "content": content}]

    sub_sections = []

    # ada teks sebelum sub-heading pertama? (kadang ada intro kalimat)
    pre_text = content[:matches[0].start()].strip()
    if pre_text:
        sub_sections.append({"heading": parent_heading, "content": pre_text})

    for i, match in enumerate(matches):
        sub_heading = f"{match.group('letter')}. {match.group('title')}".strip()
        full_heading = f"{parent_heading} > {sub_heading}"
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sub_content = content[start:end].strip()
        if sub_content:
            sub_sections.append({"heading": full_heading, "content": sub_content})

    return sub_sections


def chunk_section(heading: str, content: str, max_chars: int = 1500, overlap: int = 150) -> list[Chunk]:
    """Kalau 1 bagian masih kepanjangan, pecah lagi per kalimat dengan overlap."""
    if len(content) <= max_chars:
        return [Chunk(
            content=f"{heading}\n{content}",
            metadata={"heading": heading, "part": 1, "total_parts": 1}
        )]

    sentences = re.split(r'(?<=[.!?])\s+', content)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) > max_chars and current:
            chunks.append(current.strip())
            current = current[-overlap:] + " " + sentence
        else:
            current += " " + sentence

    if current.strip():
        chunks.append(current.strip())

    return [
        Chunk(
            content=f"{heading}\n{chunk_text}",
            metadata={"heading": heading, "part": i + 1, "total_parts": len(chunks)}
        )
        for i, chunk_text in enumerate(chunks)
    ]


def chunk_document(source_path: str, source_name: str, is_pdf: bool = True) -> list[Chunk]:
    """Entry point utama: file -> list of Chunk siap di-embed."""
    raw_text = extract_text_from_pdf(source_path) if is_pdf else extract_text_from_txt(source_path)

    level1_sections = split_level1(raw_text)

    all_chunks = []
    for section in level1_sections:
        level2_sections = split_level2(section["heading"], section["content"])
        for sub in level2_sections:
            chunks = chunk_section(sub["heading"], sub["content"])
            for c in chunks:
                c.metadata["source_document"] = source_name
                all_chunks.append(c)

    return all_chunks


if __name__ == "__main__":
    chunks = chunk_document("/home/naziri/Desktop/my_python/andora-be/templates/documents/JUKNIS_KALTIM_TUNTAS.pdf", "juknis_kaltim_tuntas", is_pdf=True)

    print(f"=== TOTAL CHUNKS: {len(chunks)} ===\n")
    for i, c in enumerate(chunks):
        print(f"--- Chunk {i+1} ---")
        print(f"Heading   : {c.metadata['heading']}")
        print(f"Panjang   : {len(c.content)} karakter")
        print(f"Preview   : {c.content[:].replace(chr(10), ' ')}...")
        print()