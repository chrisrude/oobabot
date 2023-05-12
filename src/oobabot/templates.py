import typing

from oobabot.fancy_logging import get_logger
from oobabot.types import TemplateToken
from oobabot.types import Templates


class TemplateMessageFormatter:
    # Purpose: format messages using a template string

    def __init__(
        self,
        template_name: Templates,
        template: str,
        allowed_tokens: typing.List[TemplateToken],
    ):
        self._validate_format_string(template_name, template, allowed_tokens)
        self.template_name = template_name
        self.template = template
        self.allowed_tokens = allowed_tokens

    def format(self, format_args: dict[TemplateToken, str]) -> str:
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

        get_logger().debug(
            f"validating template {template_name} with allowed args {allowed_args}"
        )
        get_logger().debug(f"template: {format_str}")

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


class TemplateStore:
    # Purpose: store templates and format messages using them

    # mapping of template names to tokens allowed in that template
    TEMPLATES: typing.Dict[Templates, typing.List[TemplateToken]] = {
        Templates.PROMPT: [
            TemplateToken.AI_NAME,
            TemplateToken.IMAGE_COMING,
            TemplateToken.MESSAGE_HISTORY,
            TemplateToken.PERSONA,
        ],
        Templates.PROMPT_HISTORY_LINE: [
            TemplateToken.USER_MESSAGE,
            TemplateToken.USER_NAME,
        ],
        Templates.PROMPT_IMAGE_COMING: [
            TemplateToken.AI_NAME,
        ],
        Templates.IMAGE_DETACH: [
            TemplateToken.IMAGE_PROMPT,
            TemplateToken.USER_NAME,
        ],
        Templates.IMAGE_CONFIRMATION: [
            TemplateToken.IMAGE_PROMPT,
            TemplateToken.USER_NAME,
        ],
        Templates.IMAGE_UNAUTHORIZED: [TemplateToken.USER_NAME],
    }

    def __init__(self):
        self.templates: typing.Dict[Templates, TemplateMessageFormatter] = {}

    def add_template(
        self,
        template_name: Templates,
        format_str: str,
        allowed_tokens: typing.List[TemplateToken],
    ):
        self.templates[template_name] = TemplateMessageFormatter(
            template_name, format_str, allowed_tokens
        )

    def format(
        self, template_name: Templates, format_args: dict[TemplateToken, str]
    ) -> str:
        return self.templates[template_name].format(format_args)
