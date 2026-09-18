import logging

from livekit import rtc
from livekit.agents import Agent, StopResponse

from app.agent.prompt import SYSTEM_PROMPT
from app.agent.tools.document_tools import eksekusi_cetak_dokumen, siapkan_pengisian_dokumen
from app.agent.tools.kirim_dokumen import kirim_dokumen
from app.agent.tools.read_document import read_uploaded_document
from app.agent.tools.search_knowledge import search_knowledge
from app.voice_models import create_realtime_model
from app.voice_turns import handle_completed_turn

logger = logging.getLogger("andora.voice")
VOICE_TOOLS = [
    search_knowledge,
    read_uploaded_document,
    siapkan_pengisian_dokumen,
    eksekusi_cetak_dokumen,
    kirim_dokumen,
]


class PersistenceAgent(Agent):
    def __init__(
        self,
        conversation_id: str | None,
        user_id: str,
        console_history: list[dict[str, str]],
        local_participant: rtc.LocalParticipant | None = None,
        destination_identity: str | None = None,
        realtime: bool = False,
    ) -> None:
        super().__init__(
            instructions=SYSTEM_PROMPT,
            tools=VOICE_TOOLS,
            llm=create_realtime_model() if realtime else None,
        )
        self._conversation_id = conversation_id
        self._user_id = user_id
        self._console_history = console_history
        self._local_participant = local_participant
        self._destination_identity = destination_identity
        self._realtime = realtime

    async def on_enter(self) -> None:
        logger.info(f"PersistenceAgent entered session with tools: {[t.info.name for t in self.tools]}")

        @self.session.on("function_tools_executed")
        def _on_tools_executed(ev):
            for fc, fco in zip(ev.function_calls, ev.function_call_outputs):
                logger.info(f"==> [TOOL EXECUTED] {fc.name}({fc.arguments}) -> output length: {len(str(fco.output))}")

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        if self._realtime:
            return
        try:
            await handle_completed_turn(
                session=self.session,
                transcript=new_message.text_content,
                conversation_id=self._conversation_id,
                user_id=self._user_id,
                console_history=self._console_history,
                local_participant=self._local_participant,
                destination_identity=self._destination_identity,
            )
        except RuntimeError as error:
            if "AgentSession is closing" not in str(error):
                raise
            logger.info("Voice response skipped because session is closing")
        except Exception:
            logger.exception("Voice turn failed")
            self.session.say(
                "Maaf, terjadi kendala. Silakan coba lagi.",
                allow_interruptions=True,
                add_to_chat_ctx=False,
            )
        raise StopResponse()
