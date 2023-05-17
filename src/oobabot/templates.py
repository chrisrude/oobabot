# -*- coding: utf-8 -*-
import enum
import functools
import textwrap
import typing


@functools.total_ordering
class Templates(enum.Enum):
    COMMAND_LOBOTOMIZE_RESPONSE = "command_lobotomize_response"

    IMAGE_DETACH = "image_detach"
    IMAGE_CONFIRMATION = "image_confirmation"
    IMAGE_GENERATION_ERROR = "image_generation_error"
    IMAGE_UNAUTHORIZED = "image_unauthorized"

    PROMPT = "prompt"
    PROMPT_HISTORY_LINE = "prompt_history_line"
    PROMPT_IMAGE_COMING = "prompt_image_coming"

    def __str__(self) -> str:
        return self.value

    def __lt__(self, other: "Templates") -> bool:
        return str(self.value) < str(other.value)


class TemplateToken(str, enum.Enum):
    AI_NAME = "AI_NAME"
    PERSONA = "PERSONA"
    IMAGE_COMING = "IMAGE_COMING"
    IMAGE_PROMPT = "IMAGE_PROMPT"
    MESSAGE_HISTORY = "MESSAGE_HISTORY"
    USER_MESSAGE = "USER_MESSAGE"
    USER_NAME = "USER_NAME"

    def __str__(self):
        return "{" + self.value + "}"


class TemplateStore:
    # Purpose: store templates and format messages using them

    # mapping of template names to tokens allowed in that template
    TEMPLATES: typing.Dict[Templates, typing.Tuple[typing.List[TemplateToken], str]] = {
        Templates.COMMAND_LOBOTOMIZE_RESPONSE: (
            [
                TemplateToken.AI_NAME,
                TemplateToken.USER_NAME,
            ],
            "Displayed in Discord after a successful /lobotomize command.  "
            + "Both the discord users and the bot AI will see this message.",
        ),
        Templates.PROMPT: (
            [
                TemplateToken.AI_NAME,
                TemplateToken.IMAGE_COMING,
                TemplateToken.MESSAGE_HISTORY,
                TemplateToken.PERSONA,
            ],
            "The main prompt sent to Oobabooga to generate a resonse from "
            + "the bot AI.  The AI's reply to this prompt will be sent to "
            + "discord as the bot's response.",
        ),
        Templates.PROMPT_HISTORY_LINE: (
            [
                TemplateToken.USER_MESSAGE,
                TemplateToken.USER_NAME,
            ],
            "Part of the AI response-generation prompt, this is used to "
            + "render a single line of chat history.  A list of these, "
            + "one for each past chat message, will become {MESSAGE_HISTORY} "
            + "and inserted into the main prompt",
        ),
        Templates.PROMPT_IMAGE_COMING: (
            [
                TemplateToken.AI_NAME,
            ],
            "Part of the AI response-generation prompt, this is used to "
            + "inform the AI that it is in the process of generating an "
            + "image.",
        ),
        Templates.IMAGE_DETACH: (
            [
                TemplateToken.IMAGE_PROMPT,
                TemplateToken.USER_NAME,
            ],
            "Shown in Discord when the user selects to discard an image "
            + "that Stable Diffusion had generated.",
        ),
        Templates.IMAGE_CONFIRMATION: (
            [
                TemplateToken.IMAGE_PROMPT,
                TemplateToken.USER_NAME,
            ],
            "Shown in Discord when an image is first generated from "
            + "Stable Diffusion.  This should prompt the user to either "
            + "save or discard the image.",
        ),
        Templates.IMAGE_GENERATION_ERROR: (
            [
                TemplateToken.IMAGE_PROMPT,
                TemplateToken.USER_NAME,
            ],
            "Shown in Discord when the we could not contact Stable Diffusion "
            + "to generate an image.",
        ),
        Templates.IMAGE_UNAUTHORIZED: (
            [TemplateToken.USER_NAME],
            "Shown in Discord privately to a user if they try to regenerate "
            "an image that was requested by someone else.",
        ),
    }

    DEFAULT_TEMPLATES: typing.Dict[Templates, str] = {
        Templates.PROMPT: textwrap.dedent(
            """
            You are in a chat room with multiple participants.
            Below is a transcript of recent messages in the conversation.
            Write the next one to three messages that you would send in this
            conversation, from the point of view of the participant named
            {AI_NAME}.

            {PERSONA}

            All responses you write must be from the point of view of
            {AI_NAME}.
            ### Transcript:
            {MESSAGE_HISTORY}
            {IMAGE_COMING}
            """
        ),
        Templates.PROMPT_HISTORY_LINE: textwrap.dedent(
            """
            {USER_NAME} says:
            {USER_MESSAGE}

            """
        ),
        Templates.PROMPT_IMAGE_COMING: textwrap.dedent(
            """
            {AI_NAME}: is currently generating an image, as requested.
            """
        ),
        Templates.IMAGE_DETACH: textwrap.dedent(
            """
            {USER_NAME} asked for an image with the prompt:
                '{IMAGE_PROMPT}'
            ...but couldn't find a suitable one.
            """
        ),
        Templates.IMAGE_CONFIRMATION: textwrap.dedent(
            """
            {USER_NAME}, is this what you wanted?
            If no choice is made, this message will 💣 self-destuct 💣 in 3 minutes.
            """
        ),
        Templates.IMAGE_GENERATION_ERROR: textwrap.dedent(
            """
            Something went wrong generating your image.  Sorry about that!
            """
        ),
        Templates.IMAGE_UNAUTHORIZED: textwrap.dedent(
            """
            Sorry, only {USER_NAME} can press the buttons.
            """
        ),
        Templates.COMMAND_LOBOTOMIZE_RESPONSE: textwrap.dedent(
            """
            Ummmm... what were we talking about?
            """
        ),
    }

    def __init__(self, settings: dict):
        self.templates: typing.Dict[Templates, TemplateMessageFormatter] = {}
        for template, (tokens, purpose) in self.TEMPLATES.items():
            template_name = str(template)
            template_fmt = settings[template_name]
            if template_fmt is None:
                raise ValueError(f"Template {template_name} has no default format")
            self.add_template(template, template_fmt, tokens, purpose)

    def add_template(
        self,
        template_name: Templates,
        format_str: str,
        allowed_tokens: typing.List[TemplateToken],
        purpose: str,
    ):
        self.templates[template_name] = TemplateMessageFormatter(
            template_name,
            format_str,
            allowed_tokens,
            purpose,
        )

    def format(
        self, template_name: Templates, format_args: typing.Dict[TemplateToken, str]
    ) -> str:
        return self.templates[template_name].format(format_args)


class TemplateMessageFormatter:
    # Purpose: format messages using a template string

    def __init__(
        self,
        template_name: Templates,
        template: str,
        allowed_tokens: typing.List[TemplateToken],
        purpose: str,
    ):
        self._validate_format_string(template_name, template, allowed_tokens)
        self.template_name = template_name
        self.template = template
        self.allowed_tokens = allowed_tokens
        self.purpose = purpose

    def __str__(self):
        return self.template

    def format(self, format_args: typing.Dict[TemplateToken, str]) -> str:
        return self.template.format(**format_args)

    @staticmethod
    def _validate_format_string(
        template_name: Templates,
        format_str: str,
        allowed_args: typing.List[TemplateToken],
    ):
        def find_all_ch(s: str, ch: str) -> typing.Generator[int, None, None]:
            # find all indices of ch in s
            for i, ltr in enumerate(s):
                if ltr == ch:
                    yield i

        # raises if fmt_string contains any args not in allowed_args
        allowed_close_brace_indices: typing.Set[int] = set()

        for open_brace_idx in find_all_ch(format_str, "{"):
            for allowed_arg in allowed_args:
                idx_end = open_brace_idx + len(allowed_arg) + 1
                next_substr = format_str[open_brace_idx : idx_end + 1]
                if next_substr == "{" + allowed_arg + "}":
                    allowed_close_brace_indices.add(idx_end)
                    break
            else:
                raise ValueError(
                    f"invalid template: {template_name} contains "
                    + f"an argument not in {allowed_args}"
                )
        for close_brace_idx in find_all_ch(format_str, "}"):
            if close_brace_idx not in allowed_close_brace_indices:
                raise ValueError(
                    f"invalid template: {template_name} contains "
                    + f"an argument not in {allowed_args}"
                )
