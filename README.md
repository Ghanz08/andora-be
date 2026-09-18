# ANDORA Backend

Voice-first AI assistant backend for Indonesian public administration procedures.

## Core Scope (MVP)

- **FastAPI**: REST API for conversations, recent sessions, and LiveKit tokens.
- **Supabase Auth & PostgreSQL**: Authenticated persistence (`conversations` & `messages`) with ownership enforcement and RLS.
- **9router Gateway**: OpenAI-compatible LLM abstraction with TTS-optimized conversational system prompt.
- **LiveKit**: Realtime audio transport with secure short-lived access tokens mapped to persistent conversations.

---

## Project Structure

```
andora-be/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── api/
│   │   ├── deps.py
│   │   ├── health.py
│   │   ├── livekit.py
│   │   └── conversations.py
│   ├── agent/
│   │   ├── agent.py
│   │   └── prompt.py
│   └── integrations/
│       ├── livekit.py
│       ├── ninerouter.py
│       └── supabase.py
├── supabase/
│   └── migrations/
│       └── 20260918000000_create_conversations_and_messages.sql
├── tests/
│   └── test_api.py
├── .env.example
├── pyproject.toml
└── README.md
```

---

## Getting Started

### 1. Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

### 2. Run Migrations

Run SQL migration in `supabase/migrations/` via Supabase Dashboard or CLI:

```bash
supabase db reset # or supabase migration up
```

### 3. Run FastAPI

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Run Voice Worker

Open a second terminal and run the LiveKit agent worker:

```bash
./.venv/bin/python -m app.voice_agent dev
```

The worker uses LiveKit Inference for Indonesian STT/TTS and keeps 9router as the only LLM gateway. It processes only final STT transcripts. Room names must follow `andora-{conversation_id}`.

### 5. Test with Postman and KITT

1. Import `ANDORA.postman_collection.json` into Postman.
2. Run Supabase login, then create a conversation.
3. Run `Create LiveKit Token` and copy `server_url`, `participant_token`, and `room_name` from the response.
4. Keep FastAPI and the voice worker running. Wait until the worker logs show a successful LiveKit registration. A `401` means `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` do not belong to the same LiveKit Cloud project.
5. Open [KITT](https://kitt.livekit.io/) and connect using `server_url` and `participant_token` if prompted.
6. Allow microphone access and speak after the greeting.
7. Verify the worker logs show a final transcript and the conversation history contains one user message and one assistant message.

Never paste `LIVEKIT_API_SECRET` into KITT or frontend code. KITT only needs the participant token returned by the backend. The participant token expires after 15 minutes.

### 6. Run Tests

```bash
PYTHONPATH=. ./.venv/bin/pytest -v
```
