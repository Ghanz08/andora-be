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

The worker uses Deepgram Nova-3 through LiveKit Inference for Indonesian STT, Cartesia Sonic-3 via LiveKit Inference for TTS, and 9router as the only LLM gateway. Turn detection is automatic (`turn_detection="stt"`), so the client should publish microphone audio continuously while connected instead of using push-to-talk RPC. Room names must follow `andora-{conversation_id}`.

### 5. Test Voice Locally

Use console mode for a local microphone and speaker test:

```bash
./.venv/bin/python -m app.voice_agent console
```

Console mode uses temporary in-memory conversation history because its internal room is named `console-room`. It does not write messages to Supabase and does not create fake database users. Speak after the greeting and confirm that you hear the 9router response through TTS.

For the persistent Cloud flow, keep FastAPI and the worker running, then use `ANDORA.postman_collection.json` to create a conversation and obtain its room token. A custom frontend must join with that token; the public KITT demo does not expose a field for a custom participant token.

Never expose `LIVEKIT_API_SECRET` to client code.

### 6. Authenticated App Flow

Google SSO is the primary user login for the mobile app. The React Native app should sign in with Google, exchange the Google ID token with Supabase Auth, then send the Supabase access token to this backend. The backend does not accept Google ID tokens directly.

Required Supabase Auth setup:

- Enable Google provider in Supabase Dashboard.
- Configure Google OAuth client IDs/secrets in Supabase.
- Keep `SUPABASE_URL` and `SUPABASE_ANON_KEY` available to the mobile app.
- Keep `SUPABASE_SERVICE_ROLE_KEY` server-only if used by this backend.

Backend contract:

1. Client app signs in with Google through Supabase Auth and keeps the Supabase access token.
2. Client app calls `POST /conversations` with `Authorization: Bearer <supabase_access_token>`.
3. Client app calls `POST /livekit/token` with the same bearer token and `{ "conversation_id": "..." }`.
4. Client app joins `room_name` from the response with `participant_token` from the response.
5. Client app publishes microphone audio continuously while connected.
6. Worker persists Gemini realtime user and assistant conversation items to Supabase.
7. Worker publishes LiveKit data packet topic `andora.turn.completed` to the owner identity after persistence succeeds.
8. Client app updates UI from `andora.turn.completed`, then calls authenticated `GET /conversations/{conversation_id}` for canonical metadata plus messages.

### 7. API Contract for Frontend

All authenticated backend requests require this header:

```http
Authorization: Bearer <supabase_access_token>
```

Do not send the Google ID token to the backend. Google ID token is only for Supabase Auth token exchange on the React Native side.

#### `GET /health`

No auth required.

Response `200`:

```json
{"status":"ok"}
```

#### `POST /conversations`

Create a persistent conversation for the authenticated Supabase user.

Request body:

```json
{"title":"Percakapan Baru"}
```

Response `201`:

```json
{
  "id": "conversation-uuid",
  "user_id": "supabase-user-uuid",
  "title": "Percakapan Baru",
  "last_message_preview": null,
  "last_message_at": "2026-09-18T10:30:00+00:00",
  "created_at": "2026-09-18T10:30:00+00:00",
  "updated_at": "2026-09-18T10:30:00+00:00"
}
```

#### `GET /conversations?search=<query>`

List recent conversations for the authenticated user. `search` is optional and searches title plus message content.

Response `200`:

```json
[
  {
    "id": "conversation-uuid",
    "user_id": "supabase-user-uuid",
    "title": "Percakapan Baru",
    "last_message_preview": "Andora: Baik...",
    "last_message_at": "2026-09-18T10:31:00+00:00",
    "created_at": "2026-09-18T10:30:00+00:00",
    "updated_at": "2026-09-18T10:31:00+00:00"
  }
]
```

#### `GET /conversations/{conversation_id}`

Get one conversation plus chronological messages. Returns `404` if the conversation does not belong to the authenticated user.

Response `200`:

```json
{
  "id": "conversation-uuid",
  "user_id": "supabase-user-uuid",
  "title": "Percakapan Baru",
  "last_message_preview": "Andora: Baik...",
  "last_message_at": "2026-09-18T10:31:00+00:00",
  "created_at": "2026-09-18T10:30:00+00:00",
  "updated_at": "2026-09-18T10:31:00+00:00",
  "messages": [
    {
      "id": "message-uuid",
      "conversation_id": "conversation-uuid",
      "role": "user",
      "content": "Halo Andora",
      "modality": "voice",
      "created_at": "2026-09-18T10:30:30+00:00"
    }
  ]
}
```

#### `POST /conversations/{conversation_id}/messages`

Fallback text or final transcript turn endpoint. For realtime voice, React Native should prefer LiveKit room audio and then fetch canonical messages after `andora.turn.completed`.

Request body:

```json
{
  "content": "Halo Andora, saya butuh bantuan.",
  "modality": "text"
}
```

Response `200`:

```json
{
  "conversation_id": "conversation-uuid",
  "user_message": {
    "id": "message-uuid",
    "conversation_id": "conversation-uuid",
    "role": "user",
    "content": "Halo Andora, saya butuh bantuan.",
    "modality": "text",
    "created_at": "2026-09-18T10:30:30+00:00"
  },
  "assistant_message": {
    "id": "message-uuid",
    "conversation_id": "conversation-uuid",
    "role": "assistant",
    "content": "Baik, saya bantu.",
    "modality": "text",
    "created_at": "2026-09-18T10:30:32+00:00"
  }
}
```

#### `POST /livekit/token`

Create a short-lived LiveKit participant token for one owned conversation.

Request body:

```json
{"conversation_id":"conversation-uuid"}
```

Response `200`:

```json
{
  "server_url": "wss://your-project.livekit.cloud",
  "participant_token": "livekit-jwt",
  "room_name": "andora-conversation-uuid",
  "conversation_id": "conversation-uuid"
}
```

Common errors:

- `401`: missing, invalid, or expired Supabase access token.
- `404`: conversation not found or not owned by authenticated user.

#### `GET /api/documents/download/{file_name}`

Download generated administrative Word document (.docx).

- Default: returns direct attachment stream with `Content-Disposition`.
- `?redirect=true`: redirects (307) directly to the Supabase Storage public URL.

#### `POST /api/documents/upload`

Upload a PDF file (form-data: `room_name`, `file`) for the assistant to read during voice sessions.

### 8. LiveKit Data Events

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

### 9. Run Tests

```bash
PYTHONPATH=. ./.venv/bin/pytest -v
```
