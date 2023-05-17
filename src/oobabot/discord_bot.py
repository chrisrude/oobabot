# -*- coding: utf-8 -*-
# Purpose: Discord client for Rosie
#

import asyncio
import typing

import discord

from oobabot import bot_commands
from oobabot import decide_to_respond
from oobabot import discord_utils
from oobabot import fancy_logger
from oobabot import image_generator
from oobabot import ooba_client
from oobabot import prompt_generator
from oobabot import repetition_tracker
from oobabot import response_stats
from oobabot import types


class DiscordBot(discord.Client):
    def __init__(
        self,
        ooba_client: ooba_client.OobaClient,
        decide_to_respond: decide_to_respond.DecideToRespond,
        prompt_generator: prompt_generator.PromptGenerator,
        repetition_tracker: repetition_tracker.RepetitionTracker,
        response_stats: response_stats.AggregateResponseStats,
        bot_commands: bot_commands.BotCommands,
        image_generator: typing.Optional[image_generator.ImageGenerator],
        discord_settings: dict,
        persona_settings: dict,
    ):
        self.bot_commands = bot_commands
        self.decide_to_respond = decide_to_respond
        self.image_generator = image_generator
        self.ooba_client = ooba_client
        self.prompt_generator = prompt_generator
        self.repetition_tracker = repetition_tracker
        self.response_stats = response_stats

        self.ai_name = persona_settings["ai_name"]
        self.persona = persona_settings["persona"]
        self.ai_user_id = -1

        self.dont_split_responses = discord_settings["dont_split_responses"]
        self.ignore_dms = discord_settings["ignore_dms"]
        self.reply_in_thread = discord_settings["reply_in_thread"]
        self.stop_markers = discord_settings["stop_markers"]
        self.stream_responses = discord_settings["stream_responses"]

        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(intents=intents)

    async def on_ready(self) -> None:
        guilds = self.guilds
        num_guilds = len(guilds)
        num_channels = sum(len(guild.channels) for guild in guilds)

        if self.user:
            self.ai_user_id = self.user.id
            user_id_str = str(self.ai_user_id)
        else:
            user_id_str = "<unknown>"

        fancy_logger.get().info(
            "Connected to discord as %s (ID: %d)", user_id_str, self.ai_user_id
        )
        fancy_logger.get().debug(
            "monitoring %d channels across %d server(s)", num_channels, num_guilds
        )
        if self.ignore_dms:
            fancy_logger.get().debug("Ignoring DMs")
        else:
            fancy_logger.get().debug("listening to DMs")

        if self.stream_responses:
            fancy_logger.get().debug("Responses: streamed live")
        elif self.dont_split_responses:
            fancy_logger.get().debug("Responses: returned as single messages")
        else:
            fancy_logger.get().debug("Responses: streamed as separate sentences")

        if self.image_generator:
            fancy_logger.get().debug("Image generation: enabled")
        else:
            fancy_logger.get().debug("Image generation: disabled")

        fancy_logger.get().debug("AI name: %s", self.ai_name)
        fancy_logger.get().debug("AI persona: %s", self.persona)

        fancy_logger.get().debug(
            "History: %d lines ", self.prompt_generator.history_lines
        )

        fancy_logger.get().debug(
            "Stop markers: %s", ", ".join(self.stop_markers) or "<none>"
        )

        str_wakewords = (
            ", ".join(self.decide_to_respond.wakewords)
            if self.decide_to_respond.wakewords
            else "<none>"
        )
        fancy_logger.get().debug("Wakewords: %s", str_wakewords)

        # we do this at the very end because when you restart
        # the bot, it can take a while for the commands to
        # register
        try:
            # register the commands
            await self.bot_commands.on_ready(self)
        except discord.DiscordException as err:
            fancy_logger.get().warning(
                "Failed to register commands: %s (continuing without commands)", err
            )

    async def on_message(self, raw_message: discord.Message) -> None:
        try:
            message = discord_utils.discord_message_to_generic_message(raw_message)
            should_respond, is_summon = self.decide_to_respond.should_reply_to_message(
                self.ai_user_id, message
            )
            if not should_respond:
                return

            async with raw_message.channel.typing():
                await self._handle_response(message, raw_message, is_summon)

        except discord.DiscordException as err:
            fancy_logger.get().error(
                "Exception while processing message: %s", err, exc_info=True
            )

    async def _handle_response(
        self,
        message: types.GenericMessage,
        raw_message: discord.Message,
        is_summon: bool,
    ):
        image_prompt = None
        if self.image_generator is not None:
            # are we creating an image?
            image_prompt = self.image_generator.maybe_get_image_prompt(raw_message)

        result = await self.send_response(
            message=message,
            raw_message=raw_message,
            image_requested=image_prompt is not None,
        )
        if result is None:
            # we failed to create a thread that the user could
            # read our response in, so we're done here.  Abort!
            return
        message_task, response_channel = result

        # log the mention, now that we know the channel we
        # want to montior later to continue to conversation
        if isinstance(message, types.ChannelMessage):
            # this logic is weird, so let's explain it...
            #
            # we're eventually going to call log_mention()
            # if all these conditions pass.  When we do this,
            # we'll start monitoring the channel_id in the near
            # future for replies that we might respond to, unprompted.
            #
            # In the general case, we want to monitor the channel
            # only if we were summoned in it.
            #
            # However if we were summonned in a channel but are
            # creating a new thread for the answer (because of
            # the --reply-in-thread flag), we want to monitor
            # that thread, not the original channel.
            #
            if is_summon:
                if isinstance(response_channel, discord.Thread):
                    message.channel_id = response_channel.id
                self.decide_to_respond.log_mention(message)

        image_task = None
        if self.image_generator is not None and image_prompt is not None:
            image_task = await self.image_generator.generate_image(
                image_prompt,
                raw_message,
                response_channel=response_channel,
            )

        response_tasks = [
            task for task in [message_task, image_task] if task is not None
        ]
        await asyncio.wait(response_tasks)

        # there may be more than one exception, so be sure to log
        # them all before raising either of them
        raise_later = None
        for task in response_tasks:
            if task.exception() is not None:
                fancy_logger.get().error(
                    f"Exception while running {task.get_coro()} "
                    + f"response: {task.exception()}",
                    stack_info=True,
                )
                raise_later = task.exception()
        if raise_later is not None:
            raise raise_later

    async def send_response(
        self,
        message: types.GenericMessage,
        raw_message: discord.Message,
        image_requested: bool,
    ) -> typing.Optional[typing.Tuple[asyncio.Task, discord.abc.Messageable]]:
        """
        Send a response to a message.

        Returns a tuple of the task that was created to send the message,
        and the channel that the message was sent to.

        If no message was sent, the task and channel will be None.
        """
        response_channel = raw_message.channel
        if (
            self.reply_in_thread
            and isinstance(raw_message.channel, discord.TextChannel)
            and isinstance(raw_message.author, discord.Member)
        ):
            # we want to create a response thread, if possible
            # but we have to see if the user has permission to do so
            # if the user can't we wont respond at all.
            perms = raw_message.channel.permissions_for(raw_message.author)
            if perms.create_public_threads:
                response_channel = await raw_message.create_thread(
                    name=f"{self.ai_name}, replying to "
                    + f"{raw_message.author.display_name}",
                )
                fancy_logger.get().debug(
                    f"Created response thread {response_channel.name} "
                    + f"({response_channel.id}) "
                    + f"in {raw_message.channel.name}"
                )
            else:
                # This user can't create threads, so we won't resond.
                # The reason we don't respond in the channel is that
                # it can create confusion later if a second user who
                # DOES have thread-create permission replies to that
                # message.  We'd end up creating a thread for that
                # second user's response, and again for a third user,
                # etc.
                fancy_logger.get().debug("User can't create threads, not responding.")
                return None

        response_coro = self.send_response_in_channel(
            message=message,
            image_requested=image_requested,
            response_channel=response_channel,
            response_channel_id=response_channel.id,
        )
        response_task = asyncio.create_task(response_coro)
        return (response_task, response_channel)

    async def history_plus_thread_kickoff_message(
        self,
        aiter_history: typing.AsyncIterator[discord.Message],
        limit: int,
    ) -> typing.AsyncIterator[types.GenericMessage]:
        """
        When returning the history of a thread, Discord
        does not include the message that kicked off the thread.

        It will show it in the UI as if it were, but it's not
        one of the messages returned by the history iterator.

        This method attempts to return that message as well,
        if we need it.
        """
        items = 0
        last_returned = None
        async for item in aiter_history:
            last_returned = item
            yield discord_utils.discord_message_to_generic_message(item)
            items += 1
        if last_returned is not None and items < limit:
            # we've reached the beginning of the history, but
            # still have space.  If this message was a reply
            # to another message, return that message as well.
            if last_returned.reference is not None:
                ref = last_returned.reference.resolved
                if ref is not None and isinstance(ref, discord.Message):
                    yield discord_utils.discord_message_to_generic_message(ref)

    async def recent_messages_following_thread(
        self, channel: discord.abc.Messageable
    ) -> typing.AsyncIterator[types.GenericMessage]:
        history = channel.history(limit=self.prompt_generator.history_lines)
        result = self.history_plus_thread_kickoff_message(
            history,
            limit=self.prompt_generator.history_lines,
        )
        return result

    async def send_response_in_channel(
        self,
        message: types.GenericMessage,
        image_requested: bool,
        response_channel: discord.abc.Messageable,
        response_channel_id: int,
    ) -> None:
        fancy_logger.get().debug(
            "Request from %s in %s", message.author_name, message.channel_name
        )

        recent_messages = await self.recent_messages_following_thread(response_channel)

        repeated_id = self.repetition_tracker.get_throttle_message_id(
            response_channel_id
        )

        prompt_prefix = await self.prompt_generator.generate(
            ai_user_id=self.ai_user_id,
            message_history=recent_messages,
            image_requested=image_requested,
            throttle_message_id=repeated_id,
        )

        this_response_stat = self.response_stats.log_request_arrived(prompt_prefix)

        try:
            if self.stream_responses:
                generator = self.ooba_client.request_as_grouped_tokens(prompt_prefix)
                await self.render_streaming_response(
                    generator,
                    this_response_stat,
                    response_channel,
                    response_channel_id,
                )
            else:
                if self.dont_split_responses:
                    generator = self.ooba_client.request_as_string(prompt_prefix)
                else:
                    generator = self.ooba_client.request_by_sentence(prompt_prefix)
                await self.render_response(
                    generator, this_response_stat, response_channel, response_channel_id
                )

        except discord.DiscordException as err:
            fancy_logger.get().error("Error: %s", err, exc_info=True)
            self.response_stats.log_response_failure()
            return

        this_response_stat.write_to_log(f"Response to {message.author_name} done!  ")
        self.response_stats.log_response_success(this_response_stat)

    async def render_response(
        self,
        response_iterator: typing.AsyncIterator[str],
        this_response_stat: response_stats.ResponseStats,
        response_channel: discord.abc.Messageable,
        response_channel_id: int,
    ):
        async for sentence in response_iterator:
            (sentence, abort_response) = self.filter_immersion_breaking_lines(sentence)
            if abort_response:
                break
            if not sentence:
                # we can't send an empty message
                continue

            response_message = await response_channel.send(sentence)
            generic_response_message = discord_utils.discord_message_to_generic_message(
                response_message
            )
            self.repetition_tracker.log_message(
                response_channel_id, generic_response_message
            )

            this_response_stat.log_response_part()

    async def render_streaming_response(
        self,
        response_iterator: typing.AsyncIterator[str],
        this_response_stat: response_stats.ResponseStats,
        response_channel: discord.abc.Messageable,
        response_channel_id: int,
    ):
        response = ""
        last_message = None
        async for token in response_iterator:
            if "" == token:
                continue

            response += token
            (response, abort_response) = self.filter_immersion_breaking_lines(response)
            if abort_response:
                break
            if not response:
                # we can't send an empty message
                continue

            if last_message is None:
                # when we send the first message, we don't want to send a notification,
                # as it will only include the first token of the response.  This will
                # not be very useful to anyone.
                last_message = await response_channel.send(response, silent=True)
            else:
                await last_message.edit(content=response)

            this_response_stat.log_response_part()

        if last_message is None:
            raise discord.DiscordException("No response was generated")

        generic_response_message = discord_utils.discord_message_to_generic_message(
            last_message
        )
        self.repetition_tracker.log_message(
            response_channel_id, generic_response_message
        )

    def filter_immersion_breaking_lines(self, sentence: str) -> typing.Tuple[str, bool]:
        lines = sentence.split("\n")
        good_lines = []
        previous_line = ""
        abort_response = False
        for line in lines:
            # if the AI gives itself a second line, just ignore
            # the line instruction and continue
            if self.prompt_generator.bot_prompt_line == line:
                fancy_logger.get().warning(
                    "Filtered out %s from response, continuing", line
                )
                continue

            # hack: abort response if it looks like the AI is
            # continuing the conversation as someone else
            if line.endswith(" says:"):
                fancy_logger.get().warning(
                    'Filtered out "%s" from response, aborting', line
                )
                abort_response = True
                break

            if line in self.stop_markers:
                fancy_logger.get().warning(
                    'Filtered out "%s" from response, aborting', line
                )
                abort_response = True
                break

            if not line and not previous_line:
                # filter out multiple blank lines in a row
                continue

            good_lines.append(line)
        return ("\n".join(good_lines), abort_response)
