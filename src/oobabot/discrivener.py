# -*- coding: utf-8 -*-
"""
Discrivener process launcher and handler.
"""

import asyncio
import enum
import json
import signal
import typing

from oobabot import fancy_logger


class Discrivener:
    """
    Launches and handles the Discrivener process.
    """

    EXEC_PATH = "./discrivener/target/release/examples/discrivener-json"
    DISCRIVENER_MODEL = "./discrivener/ggml-base.en.bin"
    KILL_TIMEOUT = 5

    def __init__(self, handler: typing.Callable[["DiscrivenerMessage"], None]):
        self._handler: typing.Callable[["DiscrivenerMessage"], None] = handler
        self._process: typing.Optional["asyncio.subprocess.Process"] = None
        self._stderr_reading_task: typing.Optional[asyncio.Task] = None
        self._stdout_reading_task: typing.Optional[asyncio.Task] = None

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
            self.DISCRIVENER_MODEL,
        )
        await self._launch_process(args)

    async def stop(self):
        if self.is_running():
            await self._kill_process()

    def is_running(self):
        return self._process is not None

    async def _launch_process(self, args: dict):
        fancy_logger.get().info("Launching Discrivener process: %s", self.EXEC_PATH)

        self._process = await asyncio.create_subprocess_exec(
            self.EXEC_PATH,
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
            self._stderr_reading_task.cancel()
            self._stdout_reading_task.cancel()

        # terminate stdout and stderr reading tasks
        await asyncio.wait_for(self._stderr_reading_task, timeout=self.KILL_TIMEOUT)
        self._stderr_reading_task = None

        await asyncio.wait_for(self._stdout_reading_task, timeout=self.KILL_TIMEOUT)
        self._stdout_reading_task = None

    async def _read_stdout(self):
        while True:
            try:
                line_bytes = await self._process.stdout.readuntil()
            except asyncio.IncompleteReadError:
                break
            line = line_bytes.decode("utf-8").strip()
            try:
                message_list = self._json_to_message_list(line)
                for message in message_list:
                    try:
                        self._handler(message)
                    except Exception as err:
                        fancy_logger.get().error(
                            "Discrivener: error handling message: %s", err
                        )
                        raise
            except json.JSONDecodeError:
                fancy_logger.get().error("Discrivener: could not parse %s", line)

        fancy_logger.get().info("Discrivener stdout reader exited")

    async def _read_stderr(self):
        print("reading stderr")
        # loop until EOF, printing everything to stderr
        while True:
            try:
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
        fancy_logger.get().info("Discrivener stderr reader exited")

    def _json_to_message_list(self, message: str) -> typing.List["DiscrivenerMessage"]:
        message_dict = json.loads(message)
        return [
            self._json_part_to_message(name, params)
            for name, params in message_dict.items()
        ]

    def _json_part_to_message(self, message_name, params: dict) -> "DiscrivenerMessage":
        if "Connect" == message_name:
            return ConnectData(params)

        if "Reconnect" == message_name:
            data = ConnectData(params)
            data.type = DiscrivenerMessageType.RECONNECT
            return data

        if "Disconnect" == message_name:
            return DisconnectData(params)

        if "UserJoin" == message_name:
            return UserJoinData(params)

        if "TranscribedMessage" == message_name:
            return TranscribedMessage(params)

        raise ValueError(f"Unknown message type: {message_name}")


class DiscrivenerMessageType(enum.Enum):
    """
    Enumerates the different types of Discrivener messages.
    """

    CONNECT = "Connect"
    RECONNECT = "Reconnect"
    DISCONNECT = "Disconnect"
    USER_JOIN = "UserJoin"
    TRANSCRIBED_MESSAGE = "TranscribedMessage"


class DiscrivenerMessage:
    """
    Base class for all Discrivener messages.
    """

    type: DiscrivenerMessageType


class ConnectData(DiscrivenerMessage):
    """
    Represents us connecting or reconnecting to the voice channel.
    """

    channel_id: int
    guild_id: int
    session_id: str
    server: str
    ssrc: int

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

    kind: str
    reason: str
    channel_id: int
    guild_id: int
    session_id: str

    def __init__(self, data: dict):
        self.type = DiscrivenerMessageType.DISCONNECT
        self.kind = data.get("kind")
        self.reason = data.get("reason")
        self.channel_id = data.get("channel_id")
        self.guild_id = data.get("guild_id")
        self.session_id = data.get("session_id")

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
    Represents a user joining or leaving a voice channel.
    """

    user_id: int
    joined: bool

    def __init__(self, data: dict):
        self.type = DiscrivenerMessageType.USER_JOIN
        self.user_id = data.get("user_id")
        self.joined = data.get("joined")

    def __str__(self):
        joined_str = "joined" if self.joined else "left"
        return f"User #{self.user_id} {joined_str} voice channel"


class TranscribedMessageTextSegment:
    """
    Represents a single text segment of a transcribed message.
    """

    text: str
    start_offset_ms: int
    end_offset_ms: int

    def __init__(self, message: dict):
        self.text = message.get("text")
        self.start_offset_ms = message.get("start_offset_ms")
        self.end_offset_ms = message.get("end_offset_ms")

    def __repr__(self):
        return (
            f"TranscribedMessageTextSegment(text={self.text}, "
            + f"start_offset_ms={self.start_offset_ms}, "
            + f"end_offset_ms={self.end_offset_ms})"
        )


class TranscribedMessage(DiscrivenerMessage):
    """
    Represents a transcribed message.
    """

    timestamp: int
    user_id: int
    audio_duration_ms: int
    processing_time_ms: int
    segments: typing.List[TranscribedMessageTextSegment]

    def __init__(self, message: dict):
        self.type = DiscrivenerMessageType.TRANSCRIBED_MESSAGE
        self.timestamp = message.get("timestamp")
        self.user_id = message.get("user_id")
        self.audio_duration_ms = message.get("audio_duration_ms")
        self.processing_time_ms = message.get("processing_time_ms")
        self.segments = [
            TranscribedMessageTextSegment(s) for s in message.get("text_segments")
        ]

    def __repr__(self) -> str:
        return (
            f"TranscribedMessage(timestamp={self.timestamp}, "
            + f"user_id={self.user_id}, "
            + f"audio_duration_ms={self.audio_duration_ms}, "
            + f"processing_time_ms={self.processing_time_ms}, "
            + f"segments={self.segments})"
        )
