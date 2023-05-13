import typing


class GenericMessage(object):
    def __init__(
        self,
        author_id: int,
        author_name: str,
        message_id: int,
        body_text: str,
        author_is_bot: bool,
        send_timestamp: float,
    ):
        self.author_id = author_id
        self.author_name = author_name
        self.message_id = message_id
        self.body_text = body_text
        self.author_is_bot = author_is_bot
        self.send_timestamp = send_timestamp

    def is_empty(self) -> bool:
        return not self.body_text.strip()


class DirectMessage(GenericMessage):
    def __init__(self, /, **kwargs):
        super().__init__(**kwargs)


class ChannelMessage(GenericMessage):
    def __init__(self, /, channel_id: int, mentions: typing.List[int], **kwargs):
        super().__init__(**kwargs)
        self.channel_id = channel_id
        self.mentions = mentions

    def is_mentioned(self, user_id: int) -> bool:
        return user_id in self.mentions
