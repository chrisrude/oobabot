# -*- coding: utf-8 -*-
"""
Generic types for messages, used to abstract away
Discord-specific types from the rest of the code.
"""
import abc
import datetime
import enum
import typing


class GenericMessage:
    """
    Represents a message from a user.
    """

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
    """
    Represents a message sent directly to the bot.
    """


class ChannelMessage(GenericMessage):
    """
    Represents a message sent in a channel, including
    a private group chat or thread.
    """

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


class FancyAuthor:
    """
    Display information about the author of a message.
    """

    def __init__(
        self,
        user_id: int,
        author_is_bot: bool,
        author_name: str,
        author_accent_color: typing.Tuple[int, int, int],
        author_avatar_url: typing.Optional[str],
    ):
        self._user_id = user_id
        self._author_is_bot = author_is_bot
        self._author_name = author_name
        self._author_accent_color = author_accent_color
        self._author_avatar_url = author_avatar_url

    @property
    def user_id(self) -> int:
        """
        Returns the ID of the user who sent the message.
        """
        return self._user_id

    @property
    def author_is_bot(self) -> bool:
        """
        Returns whether the user who sent the message is a bot.
        """
        return self._author_is_bot

    @property
    def author_name(self) -> str:
        """
        Returns the name of the user who sent the message.
        """
        return self._author_name

    @property
    def author_accent_color(self) -> typing.Tuple[int, int, int]:
        """
        Returns the accent color of the user who sent the message.
        """
        return self._author_accent_color

    @property
    def author_avatar_url(self) -> typing.Optional[str]:
        """
        Returns the avatar URL of the user who sent the message,
        if the user has chosen one.

        Will be null if the user has not set an avatar.
        """
        return self._author_avatar_url


class DiscrivenerMessageType(str, enum.Enum):
    """
    Enumerates the different types of Discrivener messages.
    """

    CHANNEL_SILENT = "ChannelSilent"
    CONNECT = "Connect"
    DISCONNECT = "Disconnect"
    RECONNECT = "Reconnect"
    TRANSCRIPTION = "Transcription"
    USER_JOIN = "UserJoin"
    USER_LEAVE = "UserLeave"


class DiscrivenerMessage(abc.ABC):
    """
    Base class for all Discrivener messages.
    """

    @abc.abstractmethod
    def __init__(self, message: dict):
        ...

    type: DiscrivenerMessageType


# not an actual GenericMessage, but still a message
class VoiceMessage(DiscrivenerMessage):
    """
    Represents a message that we have transcribed
    from a voice channel, attributed to a user.
    """

    def __init__(
        self,
        user_id: int,
        start_time: datetime.datetime,
        duration: datetime.timedelta,
    ):
        self._user_id = user_id
        self._start_time = start_time
        self._audio_duration = duration

    @property
    def user_id(self) -> int:
        """
        Returns the user ID of the user who sent the message.
        """
        return self._user_id

    @property
    def start_time(self) -> datetime.datetime:
        """
        Returns the start time of the transcription.
        """
        return self._start_time

    @property
    def duration(self) -> datetime.timedelta:
        """
        Returns the duration of the transcription.
        """
        return self._audio_duration

    @property
    @abc.abstractmethod
    def text(self) -> str:
        """
        Returns the text of the transcription.
        """

    @property
    @abc.abstractmethod
    def is_bot(self) -> bool:
        """
        Returns whether the user who sent the message is a bot.
        """


class VoiceMessageWithTokens(VoiceMessage):
    """
    A voice message that can be broken down into tokens.
    """

    @property
    @abc.abstractmethod
    def tokens_with_confidence(self) -> typing.List[typing.Tuple[str, int]]:
        """
        Returns the tokens of the transcription, with confidence scores.
        """
