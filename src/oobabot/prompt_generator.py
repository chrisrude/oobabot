# -*- coding: utf-8 -*-
"""
Generate a prompt for the AI to respond to, given the
message history and persona.
"""
import typing
import datetime
from oobabot import fancy_logger
from oobabot import persona
from oobabot import templates
from oobabot import types


class PromptGenerator:
    """
    Purpose: generate a prompt for the AI to use, given
    the message history and persona.
    """

    # this is set by the AI, and is the maximum length
    # it will understand before it starts to ignore
    # the rest of the prompt_prefix
    # note: we don't currently measure tokens, we just
    # count characters. This is a rough estimate.
    EST_CHARACTERS_PER_TOKEN = 3

    # the estimated number of characters in a line of message history
    # this is used to roughly calculate whether we'll have enough space
    # to supply the requested number of lines of history.
    #
    # in practice, we will look at the actual number of characters to
    # see what we can fit.
    #
    # note that we're doing calculations in characters, not in tokens,
    # so even counting characters exactly is still an estimate.
    EST_CHARACTERS_PER_HISTORY_LINE = 30

    # when we're not splitting responses, each history line is
    # much larger, and it's easier to run out of token space,
    # so we use a different estimate
    EST_CHARACTERS_PER_HISTORY_LINE_NOT_SPLITTING_RESPONSES = 180

    def __init__(
        self,
        discord_settings: dict,
        oobabooga_settings: dict,
        persona: persona.Persona,
        template_store: templates.TemplateStore,
    ):
        self.dont_split_responses = discord_settings["dont_split_responses"]
        self.history_lines = discord_settings["history_lines"]
        self.token_space = oobabooga_settings["request_params"]["truncation_length"]

        self.persona = persona
        self.template_store = template_store

        self.prompt_prefix = discord_settings["prompt_prefix"]
        self.prompt_suffix = discord_settings["prompt_suffix"]
        self.reply_in_thread = discord_settings["reply_in_thread"]

        self.example_dialogue = self.template_store.format(
            templates.Templates.EXAMPLE_DIALOGUE,
            {
                templates.TemplateToken.AI_NAME: self.persona.ai_name,
            },
        ).strip()

        # this will be also used when sending message
        # to suppress sending the prompt text to the user
        self.bot_prompt_line = self.template_store.format(
            templates.Templates.PROMPT_HISTORY_LINE,
            {
                templates.TemplateToken.USER_NAME: self.prompt_prefix + self.persona.ai_name + self.prompt_suffix,
                templates.TemplateToken.USER_MESSAGE: "",
            },
        ).strip()

        self.image_request_made = self.template_store.format(
            templates.Templates.PROMPT_IMAGE_COMING,
            {
                templates.TemplateToken.AI_NAME: self.persona.ai_name,
            },
        )

        self._init_history_available_chars()

    def _init_history_available_chars(self) -> None:
        """
        Calculate the number of characters we have available
        for history, and raise an exception if we don't have
        enough.

        Raises:
            ValueError: if we don't estimate to have enough space
                for the requested number of lines of history
        """
        # the number of chars we have available for history
        # is:
        #   number of chars in token space (estimated)
        #   minus the number of chars in the prompt
        #     - without any history
        #     - but with the photo request
        #
        est_chars_in_token_space = self.token_space * self.EST_CHARACTERS_PER_TOKEN
        prompt_without_history = self._generate("", self.image_request_made, guild_name="", response_channel="")

        # how many chars might we have available for history?
        available_chars_for_history = est_chars_in_token_space - len(
            prompt_without_history
        )
        # how many chars do we need for the requested number of
        # lines of history?
        chars_per_history_line = self.EST_CHARACTERS_PER_HISTORY_LINE
        if self.dont_split_responses:
            chars_per_history_line = (
                self.EST_CHARACTERS_PER_HISTORY_LINE_NOT_SPLITTING_RESPONSES
            )

        required_history_size_chars = self.history_lines * chars_per_history_line

        if available_chars_for_history < required_history_size_chars:
            fancy_logger.get().warning(
                "AI token space is too small for prompt_prefix and history "
                + "by an estimated %d"
                + " characters.  You may lose history context.  You can save space"
                + " by shortening the persona or reducing the requested number of"
                + " lines of history.",
                required_history_size_chars - available_chars_for_history,
            )
        self.max_history_chars = available_chars_for_history

    async def _render_history(
        self,
        message_history: typing.AsyncIterator[types.GenericMessage],
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

        section_separator = self.template_store.format(
            templates.Templates.SECTION_SEPARATOR,
            {
                templates.TemplateToken.AI_NAME: self.persona.ai_name,
            },
        )

        # first we process and append the chat transcript
        async for message in message_history:
            if not message.body_text:
                continue

            line = self.template_store.format(
                templates.Templates.PROMPT_HISTORY_LINE,
                {
                    templates.TemplateToken.USER_NAME: self.prompt_prefix + message.author_name + self.prompt_suffix,
                    templates.TemplateToken.USER_MESSAGE: message.body_text,
                },
            )

            if len(line) > prompt_len_remaining:
                num_discarded_lines = self.history_lines - len(history_lines)
                fancy_logger.get().warning(
                    "ran out of prompt space, discarding {%d} lines of chat history",
                    num_discarded_lines,
                )
                prompt_len_remaining = 0
                break

            prompt_len_remaining -= len(line)
            history_lines.append(line)

        # then we append the example dialogue, if it exists, and there's room in the message history
        if len(self.example_dialogue) > 0 and prompt_len_remaining > len(section_separator):
            remaining_lines = self.history_lines - len(history_lines)

            if remaining_lines > 0:
                history_lines.append(section_separator + "\n") # append the section separator (and newline) to the top which becomes the bottom
                prompt_len_remaining -= len(section_separator) # and subtract the character budget that consumed
                # split example dialogue into lines
                example_dialogue_lines = [line + "\n" for line in self.example_dialogue.split("\n")] # keep the newlines by rebuilding the list in a comprehension

                # fill remaining quota of history lines with example dialogue lines
                # this has the effect of gradually pushing them out as the chat exceeds the history limit
                for i in range(remaining_lines):
                    # start from the end of the list since the order is reversed
                    if len(example_dialogue_lines[-1]) + len(section_separator) > prompt_len_remaining: # account for the number of characters in the section separator we will append last
                        break

                    prompt_len_remaining -= len(example_dialogue_lines[-1])
                    history_lines.append(example_dialogue_lines.pop()) # pop the last item of the list into the transcript
                    # and then break out of the loop once we run out of example dialogue
                    if not example_dialogue_lines:
                        break

        # then reverse the order of the list so it's in order again
        history_lines.reverse()
        if not self.reply_in_thread:
            history_lines[-1] = history_lines[-1].strip("\n") # strip the last newline (moved to if statement due to causing errors when 'reply in thread' is True?)
        return "".join(history_lines)

    def _generate(
        self,
        message_history_txt: str,
        image_coming: str,
        guild_name: str,
        response_channel: str,
    ) -> str:
        prompt = self.template_store.format(
            templates.Templates.PROMPT,
            {
                templates.TemplateToken.AI_NAME: self.persona.ai_name,
                templates.TemplateToken.PERSONA: self.persona.persona,
                templates.TemplateToken.MESSAGE_HISTORY: message_history_txt,
                templates.TemplateToken.SECTION_SEPARATOR: self.template_store.format(
                    templates.Templates.SECTION_SEPARATOR,
                    {
                        templates.TemplateToken.AI_NAME: self.persona.ai_name
                    },
                ),
                templates.TemplateToken.IMAGE_COMING: image_coming,
                templates.TemplateToken.GUILDNAME: guild_name,
                templates.TemplateToken.CHANNELNAME: response_channel,
                templates.TemplateToken.CURRENTDATETIME: (datetime.datetime.now().strftime("%B %d, %Y - %H:%M:%S")),
            },
        )
        prompt += self.bot_prompt_line
        return prompt

    async def generate(
        self,
        message_history: typing.Optional[typing.AsyncIterator[types.GenericMessage]],
        image_requested: bool,
        guild_name: str,
        response_channel: str,
    ) -> str:
        """
        Generate a prompt for the AI to respond to.
        """
        message_history_txt = ""
        if message_history is not None:
            message_history_txt = await self._render_history(
                message_history,
            )
        image_coming = self.image_request_made if image_requested else ""
        return self._generate(message_history_txt, image_coming, guild_name, response_channel)
