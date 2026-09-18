import json
from dotenv import load_dotenv # <-- Tambah ini
from openai import OpenAI
load_dotenv()

# 1. Fungsi RAG kamu (bisa pake mock dulu atau langsung import fungsi asli)
def search_knowledge(query: str, program: str) -> str:
    print(f"\n -> [TOOL DIPANGGIL] program='{program}', query='{query}'")
    
    # Kalo mau tes RAG asli, un-comment baris ini:
    from app.rag.retriever import retrieve, format_context
    return format_context(retrieve(query=query, program=program, top_k=3))

    # Mock response untuk tes alur:
    # return f"Data RAG ({program}): Syarat dokumen adalah KTP, KTM, dan IPK minimal 3.0."

# 2. Skema Tool yang akan dikirim ke LLM
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Cari informasi dari basis pengetahuan Juknis program beasiswa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Pertanyaan atau topik spesifik."
                    },
                    "program": {
                        "type": "string",
                        "enum": ["kaltim_tuntas", "beasiswa_unggulan"],
                        "description": "Program beasiswa. WAJIB diisi. Jika belum sebutkan, tanyakan dulu ke user."
                    }
                },
                "required": ["query", "program"]
            }
        }
    }
]

client = OpenAI() # Pastikan OPENAI_API_KEY sudah diset di environment

def run_test_chat(user_input: str):
    print(f"\nUser: {user_input}")
    messages = [{"role": "user", "content": user_input}]

    # Putaran 1: Kirim pesan user ke LLM
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools
    )
    
    msg = response.choices[0].message

    # Putaran 2: Cek apakah LLM memutuskan panggil tool
    if msg.tool_calls:
        tool_call = msg.tool_calls[0]
        args = json.loads(tool_call.function.arguments)
        
        # Eksekusi fungsi RAG
        result = search_knowledge(query=args.get("query"), program=args.get("program"))

        # Kirim balik hasil RAG ke LLM
        messages.append(msg)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result
        })

        # Putaran 3: LLM menjawab user berdasarkan hasil RAG
        final_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        print(f"Bot: {final_response.choices[0].message.content}")
    else:
        # LLM memilih tidak panggil tool (misal: tanya balik program apa)
        print(f"Bot: {msg.content}")

# --- SKENARIO UJI COBA ---
if __name__ == "__main__":
    # Skenario A: User sebutkan nama beasiswa -> Harus panggil tool
    run_test_chat("Apa aja syarat dokumen Beasiswa unggulan?")

    # Skenario B: User belum sebut nama beasiswa -> Harus tanya balik tanpa panggil tool
    # run_test_chat("Berapa minimal IPK buat mendaftar?")