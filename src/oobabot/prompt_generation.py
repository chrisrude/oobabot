# strip newlines and replace them with spaces, to make
# it harder for users to trick the UI into injecting
# other instructions, or data that appears to be from
# a different user
import typing

from oobabot.fancy_logging import get_logger
from oobabot.settings import Settings
from oobabot.types import GenericMessage
from oobabot.types import MessageTemplate
from oobabot.types import TemplateToken


class PromptGenerator:
    """
    Purpose: generate a prompt_prefix for the AI to use, given
    the message history and persona.
    """

    REQUIRED_HISTORY_SIZE_CHARS = (
        Settings.HISTORY_LINES_TO_SUPPLY * Settings.HISTORY_EST_CHARACTERS_PER_LINE
    )

    def __init__(self, ai_name: str, persona: str, settings: Settings):
        self.ai_name = ai_name
        self.persona = persona
        self.settings = settings

        self.init_image_request()
        self.init_history_available_chars()

    def init_image_request(self) -> None:
        self.image_request_made = self.settings.template_store.format(
            MessageTemplate.PROMPT_IMAGE_COMING,
            {
                TemplateToken.AI_NAME: self.ai_name,
            },
        )

    async def generate_history(
        self,
        ai_user_id: int,
        message_history: typing.AsyncIterator[GenericMessage],
        stop_before_message_id: int | None,
    ) -> str:
        # add on more history, but only if we have room
        # if we don't have room, we'll just truncate the history
        # by discarding the oldest messages first
        # this is s
        # it will understand before ignore
        #
        prompt_len_remaining = self.max_history_chars

        # history_lines is newest first, so figure out
        # how many we can take, then append them in
        # reverse order
        history_lines = []

        async for message in message_history:
            # if we've hit the throttle message, stop and don't add any
            # more history
            if stop_before_message_id and message.message_id == stop_before_message_id:
                break

            adjusted_author_name = message.author_name
            if message.author_id == ai_user_id:
                # make sure the AI always sees its persona name
                # in the transcript, even if the chat program
                # has it under a different account name
                adjusted_author_name = self.ai_name

                # hack: if the message includes the text
                # "tried to make an image with the prompt",
                # ignore it
                if "tried to make an image with the prompt" in message.body_text:
                    continue

            if not message.body_text:
                continue

            line = self.settings.template_store.format(
                MessageTemplate.PROMPT_HISTORY_LINE,
                {
                    TemplateToken.USER_NAME: adjusted_author_name,
                    TemplateToken.USER_MESSAGE: message.body_text,
                },
            )

            if len(line) > prompt_len_remaining:
                num_discarded_lines = Settings.HISTORY_LINES_TO_SUPPLY - len(
                    history_lines
                )
                get_logger().warn(
                    "ran out of prompt space, discarding "
                    + f"{num_discarded_lines} lines "
                    + "of chat history"
                )
                break

            prompt_len_remaining -= len(line)
            history_lines.append(line)

        history_lines.reverse()
        return "".join(history_lines)

    def fill_in_prompt_template(
        self,
        message_history: str | None = None,
        image_request: str | None = None,
    ) -> str:
        """
        Given a template string, fill in the kwargs
        """
        return self.settings.template_store.format(
            MessageTemplate.PROMPT,
            {
                TemplateToken.AI_NAME: self.ai_name,
                TemplateToken.PERSONA: self.persona,
                TemplateToken.MESSAGE_HISTORY: message_history or "",
                TemplateToken.IMAGE_COMING: image_request or "",
            },
        )

    def init_history_available_chars(self) -> None:
        # the number of chars we have available for history
        # is:
        #   number of chars in token space (estimated)
        #   minus the number of chars in the prompt
        #     - without any history
        #     - but with the photo request
        #
        est_chars_in_token_space = (
            Settings.OOBABOT_MAX_AI_TOKEN_SPACE
            * Settings.OOBABOT_EST_CHARACTERS_PER_TOKEN
        )
        possible_prompt = self.fill_in_prompt_template(
            message_history="",
            image_request=self.image_request_made,
        )
        max_history_chars = est_chars_in_token_space - len(possible_prompt)
        if max_history_chars < self.REQUIRED_HISTORY_SIZE_CHARS:
            raise ValueError(
                "AI token space is too small for prompt_prefix and history "
                + "by an estimated "
                + f"{self.REQUIRED_HISTORY_SIZE_CHARS - self.max_history_chars}"
                + " characters.  You may lose history context.  You can save space"
                + " by shortening the persona or reducing the requested number of"
                + " lines of history."
            )
        self.max_history_chars = max_history_chars

    async def generate(
        self,
        ai_user_id: int,
        message_history: typing.AsyncIterator[GenericMessage],
        image_requested: bool,
        throttle_message_id: int | None,
    ) -> str:
        """
        Generates a prompt_prefix for the AI to use based on the message.
        """
        prompt = self.fill_in_prompt_template(
            message_history=await self.generate_history(
                ai_user_id, message_history, throttle_message_id
            ),
            image_request=self.image_request_made if image_requested else "",
        )
        return prompt
