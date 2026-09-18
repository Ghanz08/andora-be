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
│   ├── voice_agent.py
│   ├── api/
│   │   ├── deps.py
│   │   ├── health.py
│   │   ├── livekit.py
│   │   └── conversations.py
│   ├── agent/
│   │   ├── agent.py
│   │   └── prompt.py
│   └── integrations/
│       ├── faster_whisper.py
│       ├── ninerouter.py
│       └── supabase_client.py
├── supabase/
│   └── migrations/
│       ├── 20260918000000_create_conversations_and_messages.sql
│       └── 20260918010000_correct_auth_fk_and_message_roles.sql
├── tests/
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

Run SQL migrations in `supabase/migrations/` via Supabase Dashboard or CLI:

```bash
supabase db reset # or supabase migration up
```

Do not run destructive resets against shared or production databases. Migration `20260918010000_correct_auth_fk_and_message_roles.sql` adds the `conversations.user_id -> auth.users.id` foreign key and narrows message roles to `user`/`assistant` with `NOT VALID`; validate those constraints later after checking legacy rows.

### 3. Run FastAPI

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Run Voice Worker

Open a second terminal and run the LiveKit agent worker:

```bash
./.venv/bin/python -m app.voice_agent dev
```

The worker uses local `faster-whisper` (`small`, CPU INT8) for Indonesian STT, Cartesia Sonic-3 via LiveKit Inference for TTS, and 9router as the only LLM gateway. Voice is push-to-talk: the client app must call RPC `andora.mic.hold` when the mic button is pressed and `andora.mic.release` when it is released. The mic is muted until the first hold arrives and remains muted while ANDORA processes and speaks. Room names must follow `andora-{conversation_id}`.

### 5. Test Voice Locally

Use console mode for a local microphone and speaker test:

```bash
./.venv/bin/python -m app.voice_agent console
```

Console mode uses temporary in-memory conversation history because its internal room is named `console-room`. It does not write messages to Supabase and does not create fake database users. Speak after the greeting and confirm that you hear the 9router response through TTS.

For the persistent Cloud flow, keep FastAPI and the worker running, then use `ANDORA.postman_collection.json` to create a conversation and obtain its room token. A custom frontend must join with that token; the public KITT demo does not expose a field for a custom participant token.

Never expose `LIVEKIT_API_SECRET` to client code.

### 6. Authenticated App Flow

1. Client app signs in with Supabase Auth and keeps the Supabase access token.
2. Client app calls `POST /conversations` with `Authorization: Bearer <supabase_access_token>`.
3. Client app calls `POST /livekit/token` with the same bearer token and `{ "conversation_id": "..." }`.
4. Client app joins `room_name` from the response with `participant_token` from the response.
5. Client app sends RPC `andora.mic.hold` to the real worker participant identity shown in LiveKit room participants, not to a hardcoded identity.
6. Client app sends RPC `andora.mic.release` to the same worker participant identity.
7. Worker verifies `data.caller_identity` equals the authenticated token identity, commits final STT transcript once, persists the user message and assistant message through `AndoraAgent`, then publishes a LiveKit data packet on topic `andora.turn.completed` to the owner identity.
8. Worker keeps the mic disabled while TTS plays. After playback finishes, or after an empty transcript, it publishes `andora.turn.ready`; only then should the frontend leave its processing state.
9. Client app updates UI from `andora.turn.completed`, then can call authenticated `GET /conversations/{conversation_id}` for canonical metadata plus messages.

RPC responses are immediate JSON strings:

```json
{"status":"accepted","state":"recording"}
```

Duplicate release or new hold while processing returns:

```json
{"status":"busy","state":"processing"}
```

Unauthorized callers return:

```json
{"status":"unauthorized"}
```

Turn completion event example:

```json
{
  "type": "andora.turn.completed",
  "conversation_id": "2a2d3b52-9d20-4a13-8f1d-3c29d6c3e2c1",
  "user_message": {
    "id": "8a65b9ff-0af7-4d47-a81f-79bdff1cc5a2",
    "conversation_id": "2a2d3b52-9d20-4a13-8f1d-3c29d6c3e2c1",
    "role": "user",
    "content": "Tolong bantu saya membuat surat izin kampus.",
    "modality": "voice",
    "created_at": "2026-09-18T10:30:00+00:00"
  },
  "assistant_message": {
    "id": "774fc6c7-7fc6-4d65-893a-a8536c1a54d4",
    "conversation_id": "2a2d3b52-9d20-4a13-8f1d-3c29d6c3e2c1",
    "role": "assistant",
    "content": "Baik. Surat izin kampusnya untuk kegiatan apa?",
    "modality": "voice",
    "created_at": "2026-09-18T10:30:02+00:00"
  }
}
```

This event means persistence succeeded and TTS will use the same assistant text. It does not mean audio playback has completed. To keep reliable LiveKit data packets under a conservative 14 KiB UTF-8 budget, oversized payloads are replaced with `andora.turn.completed.fetch_required` containing message IDs and `messages_url: "/conversations/{conversation_id}"`; client app must fetch that authenticated HTTP detail endpoint.

Turn-ready event example:

```json
{"type":"andora.turn.ready","conversation_id":"2a2d3b52-9d20-4a13-8f1d-3c29d6c3e2c1"}
```

Empty speech releases processing state without persistence:

```json
{"type":"andora.turn.ready","conversation_id":"2a2d3b52-9d20-4a13-8f1d-3c29d6c3e2c1","reason":"empty_transcript"}
```

Failure event example:

```json
{"type":"andora.turn.failed","conversation_id":"2a2d3b52-9d20-4a13-8f1d-3c29d6c3e2c1"}
```

### 7. Run Tests

```bash
PYTHONPATH=. ./.venv/bin/pytest -v
```
