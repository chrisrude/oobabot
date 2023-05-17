# -*- coding: utf-8 -*-
import typing


class GenericMessage:
    def __init__(
        self,
        author_id: int,
        author_name: str,
        channel_id: int,
        channel_name: str,
        message_id: int,
        reference_message_id,
        body_text: str,
        author_is_bot: bool,
        send_timestamp: float,
    ):
        self.author_id = author_id
        self.author_name = author_name
        self.message_id = message_id
        self.body_text = body_text
        self.author_is_bot = author_is_bot
        self.reference_message_id = reference_message_id
        self.send_timestamp = send_timestamp
        self.channel_id = channel_id
        self.channel_name = channel_name

    def is_empty(self) -> bool:
        return not self.body_text.strip()


class DirectMessage(GenericMessage):
    pass


class ChannelMessage(GenericMessage):
    def __init__(
        self,
        /,
        mentions: typing.List[int],
        **kwargs,
    ):
        super().__init__(**kwargs)  # type: ignore
        self.mentions = mentions

    def is_mentioned(self, user_id: int) -> bool:
        return user_id in self.mentions
