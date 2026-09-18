import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.integrations.supabase import SupabaseService

client = TestClient(app)

# In-memory mock storage for tests
MOCK_CONVERSATIONS = {}
MOCK_MESSAGES = {}


@pytest.fixture(autouse=True)
def reset_mock_db():
    MOCK_CONVERSATIONS.clear()
    MOCK_MESSAGES.clear()


@pytest.fixture(autouse=True)
def mock_supabase_service(monkeypatch):
    def mock_create_conv(user_id: str, title: str = "Percakapan Baru"):
        cid = f"conv-{len(MOCK_CONVERSATIONS) + 1}"
        now = datetime.now(timezone.utc).isoformat()
        conv = {
            "id": cid,
            "user_id": user_id,
            "title": title,
            "last_message_preview": None,
            "last_message_at": now,
            "created_at": now,
            "updated_at": now,
        }
        MOCK_CONVERSATIONS[cid] = conv
        return conv

    def mock_get_conv(conversation_id: str, user_id: str):
        conv = MOCK_CONVERSATIONS.get(conversation_id)
        if conv and conv["user_id"] == user_id:
            return conv
        return None

    def mock_list_conv(user_id: str, search: str | None = None):
        res = [c for c in MOCK_CONVERSATIONS.values() if c["user_id"] == user_id]
        if search:
            res = [c for c in res if search.lower() in c["title"].lower()]
        return sorted(res, key=lambda x: x["last_message_at"], reverse=True)

    def mock_add_msg(conversation_id: str, role: str, content: str, modality: str = "voice"):
        mid = f"msg-{len(MOCK_MESSAGES) + 1}"
        now = datetime.now(timezone.utc).isoformat()
        msg = {
            "id": mid,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "modality": modality,
            "created_at": now,
        }
        if conversation_id not in MOCK_MESSAGES:
            MOCK_MESSAGES[conversation_id] = []
        MOCK_MESSAGES[conversation_id].append(msg)

        if conversation_id in MOCK_CONVERSATIONS:
            MOCK_CONVERSATIONS[conversation_id]["last_message_preview"] = f"{role.capitalize()}: {content[:50]}"
            MOCK_CONVERSATIONS[conversation_id]["last_message_at"] = now
            MOCK_CONVERSATIONS[conversation_id]["updated_at"] = now
        return msg

    def mock_list_msgs(conversation_id: str, limit: int = 20):
        msgs = MOCK_MESSAGES.get(conversation_id, [])
        return msgs[-limit:]

    def mock_update_title(conversation_id: str, title: str):
        if conversation_id in MOCK_CONVERSATIONS:
            MOCK_CONVERSATIONS[conversation_id]["title"] = title

    monkeypatch.setattr(SupabaseService, "create_conversation", mock_create_conv)
    monkeypatch.setattr(SupabaseService, "get_conversation", mock_get_conv)
    monkeypatch.setattr(SupabaseService, "list_conversations", mock_list_conv)
    monkeypatch.setattr(SupabaseService, "add_message", mock_add_msg)
    monkeypatch.setattr(SupabaseService, "list_messages", mock_list_msgs)
    monkeypatch.setattr(SupabaseService, "update_conversation_title", mock_update_title)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_authenticated_conversation_creation():
    headers = {"Authorization": "Bearer test-user-1"}
    response = client.post("/conversations", json={"title": "Pembuatan KTP"}, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Pembuatan KTP"
    assert data["user_id"] == "test-user-1"
    assert "id" in data


def test_user_cannot_access_another_users_conversation():
    headers_user1 = {"Authorization": "Bearer test-user-1"}
    headers_user2 = {"Authorization": "Bearer test-user-2"}

    # User 1 creates conversation
    create_resp = client.post("/conversations", json={"title": "User 1 Private"}, headers=headers_user1)
    conv_id = create_resp.json()["id"]

    # User 2 attempts to get User 1's conversation
    get_resp = client.get(f"/conversations/{conv_id}", headers=headers_user2)
    assert get_resp.status_code == 404


def test_conversation_list_ordering():
    headers = {"Authorization": "Bearer test-user-1"}

    # Create two conversations
    c1 = client.post("/conversations", json={"title": "First"}, headers=headers).json()
    c2 = client.post("/conversations", json={"title": "Second"}, headers=headers).json()

    # List conversations
    resp = client.get("/conversations", headers=headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert items[0]["id"] == c2["id"]  # Most recent first


@pytest.mark.asyncio
async def test_agent_message_turn_flow():
    headers = {"Authorization": "Bearer test-user-1"}
    c = client.post("/conversations", json={"title": "Voice Session"}, headers=headers).json()
    conv_id = c["id"]

    with patch(
        "app.integrations.ninerouter.ninerouter_client.generate_response",
        new_callable=AsyncMock,
        return_value="Tentu, untuk mengurus surat keterangan Anda perlu KTP dan KK.",
    ):
        turn_resp = client.post(
            f"/conversations/{conv_id}/messages",
            json={"content": "Bagaimana cara membuat surat keterangan?", "modality": "voice"},
            headers=headers,
        )
        assert turn_resp.status_code == 200
        data = turn_resp.json()
        assert data["user_message"]["content"] == "Bagaimana cara membuat surat keterangan?"
        assert data["assistant_message"]["content"] == "Tentu, untuk mengurus surat keterangan Anda perlu KTP dan KK."

        # Verify detail includes both messages in chronological order
        detail_resp = client.get(f"/conversations/{conv_id}", headers=headers)
        detail = detail_resp.json()
        assert len(detail["messages"]) == 2
        assert detail["messages"][0]["role"] == "user"
        assert detail["messages"][1]["role"] == "assistant"
        assert "Assistant:" in detail["last_message_preview"]


def test_livekit_token_generation():
    headers = {"Authorization": "Bearer test-user-1"}
    c = client.post("/conversations", json={"title": "LiveKit Conv"}, headers=headers).json()
    conv_id = c["id"]

    resp = client.post("/livekit/token", json={"conversation_id": conv_id}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["conversation_id"] == conv_id
    assert data["room_name"] == f"andora-{conv_id}"
    assert "participant_token" in data
