# -*- coding: utf-8 -*-
"""
Discrivener process launcher and handler.
"""

import asyncio
import datetime
import enum
import json
import signal
import typing

from oobabot import fancy_logger


class Discrivener:
    """
    Launches and handles the Discrivener process.
    """

    KILL_TIMEOUT = 5

    # pylint: disable=R1732
    def __init__(
        self,
        discrivener_location: str,
        discrivener_model_location: str,
        handler: typing.Callable[["DiscrivenerMessage"], None],
        log_file: typing.Optional[str] = None,
    ):
        self._discrivener_location = discrivener_location
        self._discrivener_model_location = discrivener_model_location
        self._handler: typing.Callable[["DiscrivenerMessage"], None] = handler
        self._process: typing.Optional["asyncio.subprocess.Process"] = None
        self._stderr_reading_task: typing.Optional[asyncio.Task] = None
        self._stdout_reading_task: typing.Optional[asyncio.Task] = None
        if log_file is not None:
            self._log_file = open(log_file, "a", encoding="utf-8")
        else:
            self._log_file = None

    # pylint: enable=R1732

    async def run(
        self,
        channel_id: int,
        endpoint: str,
        guild_id: int,
        session_id: str,
        user_id: int,
        voice_token: str,
    ):
        if self.is_running():
            raise RuntimeError("Already running")

        args = (
            "--channel-id",
            str(channel_id),
            "--endpoint",
            endpoint,
            "--guild-id",
            str(guild_id),
            "--session-id",
            session_id,
            "--user-id",
            str(user_id),
            "--voice-token",
            voice_token,
            self._discrivener_model_location,
        )
        await self._launch_process(args)

    async def stop(self):
        if self.is_running():
            await self._kill_process()

    def is_running(self):
        return self._process is not None

    async def _launch_process(self, args: typing.Tuple[str, ...]):
        fancy_logger.get().info(
            "Launching Discrivener process: %s", self._discrivener_location
        )
        fancy_logger.get().debug(
            "Using Discrivener model file: %s", self._discrivener_model_location
        )

        self._process = await asyncio.create_subprocess_exec(
            self._discrivener_location,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        fancy_logger.get().info(
            "Discrivener process started, PID: %d", self._process.pid
        )

        self._stderr_reading_task = asyncio.create_task(self._read_stderr())
        self._stdout_reading_task = asyncio.create_task(self._read_stdout())

    async def _kill_process(self):
        if self._process is None:
            return
        self._process.send_signal(signal.SIGINT)
        try:
            await asyncio.wait_for(self._process.wait(), timeout=self.KILL_TIMEOUT)
            fancy_logger.get().info(
                "Discrivener process (PID %d) stopped gracefully", self._process.pid
            )

        except asyncio.TimeoutError:
            fancy_logger.get().warning(
                "Discrivener process (PID %d) did not exit after %d seconds, killing",
                self._process.pid,
                self.KILL_TIMEOUT,
            )
            self._process.kill()
            await asyncio.wait_for(self._process.wait(), timeout=self.KILL_TIMEOUT)
            fancy_logger.get().warning(
                "Discrivener process (PID %d) force-killed", self._process.pid
            )
        finally:
            self._process = None
            if self._stderr_reading_task is not None:
                self._stderr_reading_task.cancel()
            if self._stdout_reading_task is not None:
                self._stdout_reading_task.cancel()

        # terminate stdout and stderr reading tasks
        if self._stderr_reading_task is not None:
            await asyncio.wait_for(self._stderr_reading_task, timeout=self.KILL_TIMEOUT)
            self._stderr_reading_task = None

        if self._stdout_reading_task is not None:
            await asyncio.wait_for(self._stdout_reading_task, timeout=self.KILL_TIMEOUT)
            self._stdout_reading_task = None

    async def _read_stdout(self):
        while True:
            try:
                if self._process is None or self._process.stdout is None:
                    fancy_logger.get().debug(
                        "Discrivener stdout reader: _process went away, exiting"
                    )
                    break
                line_bytes = await self._process.stdout.readuntil()
            except asyncio.IncompleteReadError:
                break
            line = line_bytes.decode("utf-8").strip()

            if self._log_file is not None:
                try:
                    self._log_file.write(line + "\n")
                except (IOError, OSError) as err:
                    fancy_logger.get().warning(
                        "transcript: failed to log to file: %s", err
                    )
            try:
                message_list = self._json_to_message_list(line)
                for message in message_list:
                    self._handler(message)
            except json.JSONDecodeError:
                fancy_logger.get().error("Discrivener: could not parse %s", line)

        fancy_logger.get().info("Discrivener stdout reader exited")

    async def _read_stderr(self):
        print("reading stderr")
        # loop until EOF, printing everything to stderr
        while True:
            try:
                if self._process is None or self._process.stderr is None:
                    fancy_logger.get().debug(
                        "Discrivener stderr reader: _process went away, exiting"
                    )
                    break
                line_bytes = await self._process.stderr.readuntil()
            except asyncio.IncompleteReadError:
                break
            line = line_bytes.decode("utf-8").strip()
            if (
                "whisper_init_state: " in line
                or "whisper_init_from_file_no_state: " in line
                or "whisper_model_load: " in line
            ):
                # workaround nonsense noise in whisper.cpp
                continue
            fancy_logger.get().error("Discrivener: %s", line)

        fancy_logger.get().info("Discrivener stderr reader exited")

    def _json_to_message_list(self, message: str) -> typing.List["DiscrivenerMessage"]:
        message_dict = json.loads(message)
        result = []
        for name, params in message_dict.items():
            if name is None:
                continue
            message_part = self._json_part_to_message(name, params)
            if message_part is None:
                continue
            result.append(message_part)
        return result

    # pylint: disable=too-many-return-statements
    def _json_part_to_message(
        self, message_name, params: dict
    ) -> typing.Optional["DiscrivenerMessage"]:
        if "Connect" == message_name:
            return ConnectData(params)

        if "Reconnect" == message_name:
            data = ConnectData(params)
            data.type = DiscrivenerMessageType.RECONNECT
            return data

        if "Disconnect" == message_name:
            return DisconnectData(params)

        if "ChannelSilent" == message_name:
            return ChannelSilentData(params)

        if "UserJoin" == message_name:
            return UserJoinData(params)

        if "UserLeave" == message_name:
            return UserLeaveData(params)

        if "Transcription" == message_name:
            return Transcription(params)

        fancy_logger.get().warning("Discrivener: unknown message type %s", message_name)
        return None

    # pylint: enable=too-many-return-statements


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


class DiscrivenerMessage:
    """
    Base class for all Discrivener messages.
    """

    type: DiscrivenerMessageType


class ChannelSilentData(DiscrivenerMessage):
    """
    Represents whether any user is speaking in the channel.
    """

    def __init__(self, data: dict):
        self.type = DiscrivenerMessageType.CHANNEL_SILENT
        self.silent = bool(data)

    def __repr__(self):
        return f"ChannelSilent(silent={self.silent})"


class ConnectData(DiscrivenerMessage):
    """
    Represents us connecting or reconnecting to the voice channel.
    """

    def __init__(self, data: dict):
        self.type = DiscrivenerMessageType.CONNECT
        self.channel_id = data.get("channel_id")
        self.guild_id = data.get("guild_id")
        self.session_id = data.get("session_id")
        self.server = data.get("server")
        self.ssrc = data.get("ssrc")

    def __repr__(self):
        return (
            f"ConnectData(channel_id={self.channel_id}, "
            + f"guild_id={self.guild_id}, "
            + f"session_id={self.session_id}, "
            + f"server={self.server}, "
            + f"ssrc={self.ssrc})"
        )


class DisconnectData(DiscrivenerMessage):
    """
    Represents a disconnect from the voice channel.
    """

    def __init__(self, data: dict):
        self.type = DiscrivenerMessageType.DISCONNECT
        self.kind: str = data.get("kind")
        self.reason: str = data.get("reason")
        self.channel_id: int = data.get("channel_id")
        self.guild_id: int = data.get("guild_id")
        self.session_id: int = data.get("session_id")

    def __repr__(self):
        return (
            f"DisconnectData(kind={self.kind}, "
            + f"reason={self.reason}, "
            + f"channel_id={self.channel_id}, "
            + f"guild_id={self.guild_id}, "
            + f"session_id={self.session_id})"
        )


class UserJoinData(DiscrivenerMessage):
    """
    Represents a user joining a voice channel.
    """

    def __init__(self, data: dict):
        self.type = DiscrivenerMessageType.USER_JOIN
        self.user_id: int = data

    def __str__(self):
        return f"User #{self.user_id} joined voice channel"


class UserLeaveData(DiscrivenerMessage):
    """
    Represents a user leaving a voice channel.
    """

    def __init__(self, data: dict):
        self.type = DiscrivenerMessageType.USER_LEAVE
        self.user_id: int = data

    def __str__(self):
        return f"User #{self.user_id} left voice channel"


class TokenWithProbability:
    """
    Represents a token with a probability.
    """

    def __init__(self, data: dict):
        self.probability: int = data.get("p", 0)
        self.token_id: int = data.get("token_id", 0)
        self.token_text: str = str(data.get("token_text"))

    def __repr__(self):
        return (
            "TokenWithProbability("
            + f"probability={self.probability}, "
            + f"token_id={self.token_id}, "
            + f"token_text={self.token_text})"
        )


def to_datetime(message: dict) -> datetime.datetime:
    """
    Converts a message into a datetime object.
    """
    seconds: int = message.get("secs_since_epoch", 0)
    nanos: int = message.get("nanos_since_epoch", 0)
    return datetime.datetime.fromtimestamp(seconds + nanos / 1e9)


def to_duration(message: dict) -> datetime.timedelta:
    """
    Converts a message into a timedelta object.
    """
    seconds: int = message.get("secs", 0)
    nanos: int = message.get("nanos", 0)
    return datetime.timedelta(seconds=seconds, microseconds=nanos / 1e3)


class TextSegment:
    """
    Represents a single text segment of a transcribed message.
    """

    def __init__(self, message: dict):
        self.tokens_with_probability = [
            TokenWithProbability(data)
            for data in message.get("tokens_with_probability")
        ]
        self.start_offset_ms: int = message.get("start_offset_ms")
        self.end_offset_ms: int = message.get("end_offset_ms")

    def __repr__(self):
        return (
            f"TextSegment(tokens_with_probability={self.tokens_with_probability}, "
            + f"start_offset_ms={self.start_offset_ms}, "
            + f"end_offset_ms={self.end_offset_ms})"
        )

    def __str__(self) -> str:
        return "".join([t.token_text for t in self.tokens_with_probability])


class Transcription(DiscrivenerMessage):
    """
    Represents a transcribed message.
    """

    def __init__(self, message: dict):
        self.type = DiscrivenerMessageType.TRANSCRIPTION
        self.timestamp: datetime.datetime = to_datetime(message.get("start_timestamp"))
        self.user_id: int = message.get("user_id")
        self.audio_duration: datetime.timedelta = to_duration(
            message.get("audio_duration")
        )
        self.processing_time: datetime.timedelta = to_duration(
            message.get("processing_time")
        )
        self.segments: typing.List[TextSegment] = [
            TextSegment(s) for s in message.get("segments")
        ]
        self.latency: datetime.timedelta = datetime.datetime.now() - self.timestamp

    def __repr__(self) -> str:
        return (
            f"Transcription(timestamp={self.timestamp}, "
            + f"user_id={self.user_id}, "
            + f"audio_duration={self.audio_duration}, "
            + f"processing_time={self.processing_time}, "
            + f"segments={self.segments})"
            + f"latency={self.latency})"
        )
