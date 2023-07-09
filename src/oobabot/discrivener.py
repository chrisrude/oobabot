# -*- coding: utf-8 -*-
"""
Discrivener process launcher and handler.  Receives and
parses messages from the Discrivener process and passes
them to the handler.
"""

import asyncio
import json
import pathlib
import signal
import typing

from oobabot import discrivener_message
from oobabot import fancy_logger
from oobabot import types


class Discrivener:
    """
    Launches and handles the Discrivener process.
    """

    KILL_TIMEOUT: float = 2.0

    # pylint: disable=R1732
    def __init__(
        self,
        discrivener_location: str,
        discrivener_model_location: str,
        handler: typing.Callable[["types.DiscrivenerMessage"], None],
        log_file: typing.Optional[str] = None,
    ):
        self._discrivener_location = pathlib.Path(discrivener_location).expanduser()
        self._discrivener_model_location = pathlib.Path(
            discrivener_model_location
        ).expanduser()
        self._handler: typing.Callable[["types.DiscrivenerMessage"], None] = handler
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
            str(self._discrivener_model_location),
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
            stdin=asyncio.subprocess.PIPE,
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

    # @fancy_logger.log_async_task
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
                message = json.loads(
                    line,
                    object_pairs_hook=discrivener_message.object_pairs_hook,
                )
                self._handler(message)
            except json.JSONDecodeError:
                fancy_logger.get().error("Discrivener: could not parse %s", line)

        fancy_logger.get().info("Discrivener stdout reader exited")

    # @fancy_logger.log_async_task
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

    def speak(self, text: str):
        if self._process is None or self._process.stdin is None:
            fancy_logger.get().error("Discrivener: _process is not running")
            return

        self._process.stdin.write(text.encode("utf-8") + b"\n")
