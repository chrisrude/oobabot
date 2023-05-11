from enum import Enum


class GenericMessage:
    def __init__(self, author_id, author_name, message_id, body_text):
        self.author_id = author_id
        self.author_name = author_name
        self.message_id = message_id
        self.body_text = body_text


class MessageTemplate(Enum):
    IMAGE_DETACH = "image_detach"
    IMAGE_CONFIRMATION = "image_confirmation"

    PROMPT = "prompt"
    PROMPT_HISTORY_LINE = "prompt_history_line"
    PROMPT_IMAGE_COMING = "prompt_image_coming"


class TemplateToken(str, Enum):
    AI_NAME = "AI_NAME"
    PERSONA = "PERSONA"
    IMAGE_COMING = "IMAGE_COMING"
    IMAGE_REQUEST = "IMAGE_REQUEST"
    MESSAGE_HISTORY = "MESSAGE_HISTORY"
    USER_MESSAGE = "USER_MESSAGE"
    USER_NAME = "USER_NAME"
