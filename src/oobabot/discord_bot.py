# Purpose: Discord client for Rosie
#

import asyncio
import re
import typing

import discord

from oobabot.decide_to_respond import DecideToRespond
from oobabot.fancy_logging import get_logger
from oobabot.image_generator import ImageGenerator
from oobabot.ooba_client import OobaClient
from oobabot.prompt_generator import PromptGenerator
from oobabot.repetition_tracker import RepetitionTracker
from oobabot.response_stats import AggregateResponseStats
from oobabot.types import ChannelMessage
from oobabot.types import DirectMessage
from oobabot.types import GenericMessage

FORBIDDEN_CHARACTERS = r"[\n\r\t]"
FORBIDDEN_CHARACTERS_PATTERN = re.compile(FORBIDDEN_CHARACTERS)


def sanitize_string(raw_string: str) -> str:
    """
    Filter out any characters that would confuse the AI
    """
    return FORBIDDEN_CHARACTERS_PATTERN.sub(" ", raw_string)


def discord_message_to_generic_message(raw_message: discord.Message) -> GenericMessage:
    """
    Convert a discord message to a GenericMessage or subclass thereof
    """
    generic_args = {
        "author_id": raw_message.author.id,
        "author_name": sanitize_string(raw_message.author.name),
        "message_id": raw_message.id,
        "body_text": sanitize_string(raw_message.content),
        "author_is_bot": raw_message.author.bot,
        "send_timestamp": raw_message.created_at.timestamp(),
    }
    if isinstance(raw_message.channel, discord.DMChannel):
        return DirectMessage(**generic_args)
    if (
        isinstance(raw_message.channel, discord.TextChannel)
        or isinstance(raw_message.channel, discord.GroupChannel)
        or isinstance(raw_message.channel, discord.Thread)
    ):
        return ChannelMessage(
            channel_id=raw_message.channel.id,
            mentions=[mention.id for mention in raw_message.mentions],
            **generic_args,
        )
    get_logger().warning(
        f"Unknown channel type {type(raw_message.channel)}, "
        + f"unsolicited replies disabled.: {raw_message.channel}"
    )
    return GenericMessage(**generic_args)


async def discord_to_generic_async(
    raw_messages: typing.AsyncIterator[discord.Message],
) -> typing.AsyncIterator[GenericMessage]:
    async for raw_message in raw_messages:
        message = discord_message_to_generic_message(raw_message)
        yield message


class DiscordBot(discord.Client):
    # seconds after which we'll lazily purge a channel
    # from channel_last_direct_response

    def __init__(
        self,
        ooba_client: OobaClient,
        decide_to_respond: DecideToRespond,
        prompt_generator: PromptGenerator,
        repetition_tracker: RepetitionTracker,
        aggregate_response_stats: AggregateResponseStats,
        image_generator: ImageGenerator | None,
        ai_name: str,
        persona: str,
        ignore_dms: bool,
        dont_split_responses: bool,
        reply_in_thread: bool,
        log_all_the_things: bool,
    ):
        self.ooba_client = ooba_client
        self.decide_to_respond = decide_to_respond
        self.prompt_generator = prompt_generator
        self.repetition_tracker = repetition_tracker
        self.aggregate_response_stats = aggregate_response_stats

        self.ai_name = ai_name
        self.persona = persona
        self.ai_user_id = -1
        self.image_generator = image_generator

        self.ignore_dms = ignore_dms
        self.dont_split_responses = dont_split_responses
        self.reply_in_thread = reply_in_thread
        self.log_all_the_things = log_all_the_things

        # a list of timestamps in which we last posted to a channel
        self.channel_last_direct_response = {}

        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(intents=intents)

    async def on_ready(self) -> None:
        guilds = self.guilds
        num_guilds = len(guilds)
        num_channels = sum([len(guild.channels) for guild in guilds])

        if self.user:
            self.ai_user_id = self.user.id
            user_id_str = str(self.ai_user_id)
        else:
            user_id_str = "<unknown>"

        get_logger().info(f"Connected to discord as {self.user} (ID: {user_id_str})")
        get_logger().debug(
            f"monitoring {num_channels} channels across " + f"{num_guilds} server(s)"
        )
        if self.ignore_dms:
            get_logger().debug("Ignoring DMs")
        else:
            get_logger().debug("listening to DMs")

        if self.dont_split_responses:
            get_logger().debug("Responses: returned as single messages")
        else:
            get_logger().debug("Responses: streamed as separate sentences")

        if self.image_generator:
            get_logger().debug("Image generation: enabled")
        else:
            get_logger().debug("Image generation: disabled")

        get_logger().debug(f"AI name: {self.ai_name}")
        get_logger().debug(f"AI persona: {self.persona}")

        get_logger().debug(f"History: {self.prompt_generator.history_lines} lines ")

        str_wakewords = (
            ", ".join(self.decide_to_respond.wakewords)
            if self.decide_to_respond.wakewords
            else "<none>"
        )
        get_logger().debug(f"Wakewords: {str_wakewords}")

    async def on_message(self, raw_message: discord.Message) -> None:
        try:
            message = discord_message_to_generic_message(raw_message)
            should_respond, is_summon = self.decide_to_respond.should_reply_to_message(
                self.ai_user_id, message
            )
            if not should_respond:
                return
            async with raw_message.channel.typing():
                image_prompt = None
                if self.image_generator is not None:
                    # are we creating an image?
                    image_prompt = self.image_generator.maybe_get_image_prompt(
                        raw_message
                    )

                message_task, response_channel = await self.send_response(
                    message=message,
                    raw_message=raw_message,
                    image_requested=image_prompt is not None,
                )
                if response_channel is None:
                    # we failed to create a thread that the user could
                    # read our response in, so we're done here.  Abort!
                    return

                # log the mention, now that we know the channel
                # we want to reply to
                if is_summon and isinstance(message, ChannelMessage):
                    # we need to hack up the channel id, since it
                    # might now be a thread.  We want to watch the
                    # thread, not the original channel for unsolicited
                    # responses.
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

        except Exception as e:
            get_logger().error(
                f"Exception while processing message: {e}", exc_info=True
            )

    async def send_response(
        self,
        message: GenericMessage,
        raw_message: discord.Message,
        image_requested: bool,
    ) -> typing.Tuple[asyncio.Task | None, discord.abc.Messageable | None]:
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
                    name=f"{self.ai_name}: Response to {raw_message.author.name}",
                )
                get_logger().debug(
                    f"Created response thread {response_channel.name} "
                    f"in {raw_message.channel.name}"
                )
            else:
                # This user can't create threads, so we won't resond.
                # The reason we don't respond in the channel is that
                # it can create confusion later if a second user who
                # DOES have thread-create permission replies to that
                # message.  We'd end up creating a thread for that
                # second user's response, and again for a third user,
                # etc.
                get_logger().debug("User can't create threads, not responding.")
                return (None, None)

        response_coro = self.send_response_in_channel(
            message=message,
            raw_message=raw_message,
            image_requested=image_requested,
            response_channel=response_channel,
        )
        response_task = asyncio.create_task(response_coro)
        return (response_task, response_channel)

    async def send_response_in_channel(
        self,
        message: GenericMessage,
        raw_message: discord.Message,
        image_requested: bool,
        response_channel: discord.abc.Messageable,
    ) -> None:
        get_logger().debug(f"Request from {message.author_name}")

        recent_messages = raw_message.channel.history(
            limit=self.prompt_generator.history_lines
        )

        repeated_id = self.repetition_tracker.get_throttle_message_id(
            raw_message.channel.id
        )

        prompt_prefix = await self.prompt_generator.generate(
            ai_user_id=self.ai_user_id,
            message_history=discord_to_generic_async(recent_messages),
            image_requested=image_requested,
            throttle_message_id=repeated_id,
        )

        response_stats = self.aggregate_response_stats.log_request_arrived(
            prompt_prefix
        )
        if self.log_all_the_things:
            print("prompt_prefix:\n----------\n")
            print(prompt_prefix)
            print("Response:\n----------\n")

        try:
            if self.dont_split_responses:
                generator = self.ooba_client.request_as_string(prompt_prefix)
            else:
                generator = self.ooba_client.request_by_sentence(prompt_prefix)

            async for sentence in generator:
                if self.log_all_the_things:
                    print(sentence)

                # if the AI gives itself a second line, just ignore
                # the line instruction and continue
                if self.prompt_generator.bot_prompt_line == sentence:
                    get_logger().warning(
                        f'Filtered out "{sentence}" from response, continuing'
                    )
                    continue

                # hack: abort response if it looks like the AI is
                # continuing the conversation as someone else
                if sentence.endswith(" says:"):
                    get_logger().warning(
                        f'Filtered out "{sentence}" from response, aborting'
                    )
                    break

                response_message = await response_channel.send(sentence)
                generic_response_message = discord_message_to_generic_message(
                    response_message
                )
                self.repetition_tracker.log_message(
                    raw_message.channel.id, generic_response_message
                )

                response_stats.log_response_part()

        except Exception as err:
            get_logger().error(f"Error: {str(err)}")
            self.aggregate_response_stats.log_response_failure()
            return

        response_stats.write_to_log(f"Response to {message.author_name} done!  ")
        self.aggregate_response_stats.log_response_success(response_stats)
