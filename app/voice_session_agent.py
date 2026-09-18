import logging

from livekit import rtc
from livekit.agents import Agent, StopResponse

from app.agent.prompt import SYSTEM_PROMPT
from app.agent.tools.search_knowledge import search_knowledge
from app.voice_models import create_realtime_model
from app.voice_turns import handle_completed_turn

logger = logging.getLogger("andora.voice")


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
            tools=[search_knowledge],
            llm=create_realtime_model() if realtime else None,
        )
        self._conversation_id = conversation_id
        self._user_id = user_id
        self._console_history = console_history
        self._local_participant = local_participant
        self._destination_identity = destination_identity
        self._realtime = realtime

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
