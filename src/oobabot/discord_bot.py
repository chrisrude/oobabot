# Purpose: Discord client for Rosie
#

import asyncio
import random
import re
import time
import typing

import discord

from oobabot.fancy_logging import get_logger
from oobabot.image_view import send_image
from oobabot.ooba_client import OobaClient
from oobabot.prompt_generation import PromptGenerator
from oobabot.response_stats import AggregateResponseStats
from oobabot.sd_client import StableDiffusionClient
from oobabot.settings import Settings
from oobabot.types import GenericMessage

FORBIDDEN_CHARACTERS = r"[\n\r\t]"
FORBIDDEN_CHARACTERS_PATTERN = re.compile(FORBIDDEN_CHARACTERS)


def sanitize_string(raw_string: str) -> str:
    """
    Filter out any characters that are not commonly on a
    US-English keyboard
    """
    return FORBIDDEN_CHARACTERS_PATTERN.sub(" ", raw_string)


def discord_message_to_generic_message(raw_message: discord.Message) -> GenericMessage:
    """
    Convert a discord message to a GenericMessage
    """
    return GenericMessage(
        raw_message.author.id,
        sanitize_string(raw_message.author.name),
        raw_message.id,
        sanitize_string(raw_message.content),
    )


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
        settings: Settings,
        stable_diffusion_client: StableDiffusionClient | None = None,
    ):
        self.ooba_client = ooba_client

        self.ai_name = settings.ai_name
        self.persona = settings.persona
        self.ai_user_id = -1
        self.wakewords = settings.wakewords
        self.log_all_the_things = settings.log_all_the_things
        self.ignore_dms = settings.ignore_dms
        self.settings = settings

        # a list of timestamps in which we last posted to a channel
        self.channel_last_direct_response = {}

        self.discard_last_response_after_seconds = max(
            time for time, _ in Settings.DISCORD_TIME_VS_RESPONSE_CHANCE
        )

        # attempts to detect when the bot is stuck in a loop, and will try to
        # stop it by limiting the history it can see
        self.repetition_tracker = RepetitionTracker()

        self.average_stats = AggregateResponseStats(ooba_client)
        self.prompt_prefix_generator = PromptGenerator(
            self.ai_name, self.persona, settings
        )

        # match messages that include any `wakeword`, but not as part of
        # another word
        self.wakeword_patterns = [
            re.compile(rf"\b{wakeword}\b", re.IGNORECASE) for wakeword in self.wakewords
        ]

        photowords = ["drawing", "photo", "pic", "picture", "image", "sketch"]
        self.photo_patterns = [
            re.compile(
                r"^.*\b" + photoword + r"\b[\s]*(of|with)?[\s]*[:]?(.*)$", re.IGNORECASE
            )
            for photoword in photowords
        ]

        self.stable_diffusion_client = stable_diffusion_client

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

        get_logger().debug(f"AI name: {self.ai_name}")
        get_logger().debug(f"AI persona: {self.persona}")

        str_wakewords = ", ".join(self.wakewords) if self.wakewords else "<none>"
        get_logger().debug(f"wakewords: {str_wakewords}")

    async def start(self) -> None:
        # todo: join these at a higher level?
        if self.stable_diffusion_client is not None:
            async with self.stable_diffusion_client:
                await self._inner_start()
        else:
            await self._inner_start()

    async def _inner_start(self):
        async with self.ooba_client:
            try:
                await super().start(self.settings.DISCORD_TOKEN)
            except discord.LoginFailure:
                get_logger().error("Failed to log in to discord.  Check your token?")
            return

    def should_send_direct_response(self, message: discord.Message) -> bool:
        """
        Returns true if the bot was directly addressed in the message,
        and will respond.
        """

        # reply to all private messages
        if discord.ChannelType.private == message.channel.type:
            if self.ignore_dms:
                return False
            return True

        # reply to all messages that include a wakeword
        for wakeword_pattern in self.wakeword_patterns:
            if wakeword_pattern.search(message.content):
                return True

        # reply to all messages in which we're @-mentioned
        if self.user and self.user.id in [m.id for m in message.mentions]:
            return True

        return False

    def should_send_unsolicited_response(self, message: discord.Message) -> bool:
        # if we haven't posted to this channel recently, don't reply
        if message.channel.id not in self.channel_last_direct_response:
            return False

        time_since_last_send = (
            message.created_at.timestamp()
            - self.channel_last_direct_response[message.channel.id]
        )

        # return a base chance that we'll respond to a message that wasn't
        # addressed to us, based on the table in TIME_VS_RESPONSE_CHANCE.
        # other factors might increase this chance.
        response_chance = 0.0
        for duration, chance in Settings.DISCORD_TIME_VS_RESPONSE_CHANCE:
            if time_since_last_send < duration:
                response_chance = chance
                break

        # if the new message ends with a question mark, we'll respond
        if message.content.endswith("?"):
            response_chance += Settings.DISCORD_INTERROBANG_BONUS

        # if the new message ends with an exclamation point, we'll respond
        if message.content.endswith("!"):
            response_chance += Settings.DISCORD_INTERROBANG_BONUS

        if random.random() < response_chance:
            return True

        return False

    def purge_outdated_response_times(self) -> None:
        oldest_time_to_keep = time.time() - self.discard_last_response_after_seconds
        self.channel_last_direct_response = {
            channel_id: response_time
            for channel_id, response_time in self.channel_last_direct_response.items()
            if response_time >= oldest_time_to_keep
        }

    def should_reply_to_message(self, message: discord.Message) -> bool:
        # ignore messages from other bots, out of fear of infinite loops,
        # as well as world domination
        if message.author.bot:
            return False

        # we do not want the bot to reply to itself.  This is redundant
        # with the previous check, except it won't be if someone decides
        # to run this under their own user token, rather than a proper
        # bot token.
        if self.user and message.author.id == self.user.id:
            return False

        if self.should_send_direct_response(message):
            # store the timestamp of this response in channel_last_direct_response
            if message.channel.id:
                self.channel_last_direct_response[message.channel.id] = time.time()
            return True

        ################################################################
        # end of "solicited" response checks.  From here on out, we're
        # only responding to messages that weren't directly addressed
        # to us.

        # if we're not at-mentioned but others are, don't reply
        if message.mentions:
            return False

        # if message is empty, don't reply.  This can happen if someone
        # posts an image or an attachment without a comment.
        if not message.content.strip():
            return False

        # if we've posted recently in this channel, there are a few
        # other reasons we may respond.  But if we haven't, just
        # ignore the message.

        # purge any channels that we haven't posted to in a while
        self.purge_outdated_response_times()

        # we're now in the set of spaces where we have a chance of
        # responding to a message that wasn't directly addressed to us

        if self.should_send_unsolicited_response(message):
            return True

        # ignore anything else
        return False

    def log_stats(self) -> None:
        self.average_stats.write_stat_summary_to_log()

    def make_photo_prompt_from_message(
        self, raw_message: discord.Message
    ) -> str | None:
        for photo_pattern in self.photo_patterns:
            sanitized_content = sanitize_string(raw_message.content)
            match = photo_pattern.search(sanitized_content)
            if match:
                return match.group(2)

    async def request_picture_generation(
        self, photo_prompt: str, raw_message: discord.Message
    ) -> bool:
        async def wrapped_send_image() -> None:
            if self.stable_diffusion_client is None:
                raise ValueError("No stable diffusion client")
            try:
                await send_image(
                    self.stable_diffusion_client,
                    raw_message,
                    photo_prompt,
                    self.settings,
                )
            except Exception as e:
                get_logger().error(f"Exception while sending image: {e}", exc_info=True)

        asyncio.create_task(wrapped_send_image())
        return True

    async def on_message(self, raw_message: discord.Message) -> None:
        try:
            if not self.should_reply_to_message(raw_message):
                return
        except Exception as e:
            get_logger().error(f"Exception while checking message: {e}", exc_info=True)
            return
        try:
            async with raw_message.channel.typing():
                photo_requested = False
                if self.stable_diffusion_client is not None:
                    photo_prompt = self.make_photo_prompt_from_message(raw_message)
                    if photo_prompt is not None:
                        photo_requested = await self.request_picture_generation(
                            photo_prompt, raw_message
                        )

                await self.send_response(raw_message, photo_requested)
        except Exception as e:
            get_logger().error(f"Exception while sending response: {e}", exc_info=True)

    async def send_response(
        self, raw_message: discord.Message, photo_requested: bool
    ) -> None:
        message = discord_message_to_generic_message(raw_message)
        get_logger().debug(f"Request from {message.author_name}")

        recent_messages = raw_message.channel.history(
            limit=Settings.HISTORY_LINES_TO_SUPPLY
        )

        repeated_id = self.repetition_tracker.get_throttle_message_id(
            raw_message.channel.id
        )

        prompt_prefix = await self.prompt_prefix_generator.generate(
            self.ai_user_id,
            discord_to_generic_async(recent_messages),
            photo_requested,
            repeated_id,
        )

        response_stats = self.average_stats.log_request_arrived(prompt_prefix)
        if self.log_all_the_things:
            print("prompt_prefix:\n----------\n")
            print(prompt_prefix)
            print("Response:\n----------\n")

        try:
            async for sentence in self.ooba_client.request_by_sentence(prompt_prefix):
                if self.log_all_the_things:
                    print(sentence)

                # if the AI gives itself a second line, just ignore
                # the line instruction and continue
                if f"{self.ai_name} says:" == sentence:
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

                response_message = await raw_message.channel.send(sentence)
                self.repetition_tracker.log_message(
                    raw_message.channel.id, response_message
                )

                response_stats.log_response_part()

        except Exception as err:
            get_logger().error(f"Error: {str(err)}")
            self.average_stats.log_response_failure()
            return

        response_stats.write_to_log(f"Response to {message.author_name} done!  ")
        self.average_stats.log_response_success(response_stats)


class RepetitionTracker:
    # how many times the bot can repeat the same thing before we
    # throttle history

    def __init__(
        self, repetition_threshold: int = Settings.DISCORD_REPETITION_THRESHOLD
    ) -> None:
        self.repetition_threshold = repetition_threshold

        # stores a map of channel_id ->
        #   (last_message, throttle_message_id, repetion_count)

        self.repetition_count: typing.Dict[int, typing.Tuple[str, int, int]] = {}

    def get_throttle_message_id(self, channel_id: int) -> int | None:
        """
        Returns the message ID of the last message that should be throttled, or None
        if no throttling is needed
        """
        _, throttle_message_id, _ = self.repetition_count.get(
            channel_id, (None, None, None)
        )
        return throttle_message_id

    def log_message(self, channel_id: int, response_message: discord.Message) -> None:
        """
        Logs a message sent by the bot, to be used for repetition tracking
        """
        # make string into canonical form
        sentence = self.make_canonical(response_message.content)

        last_message, throttle_message_id, repetition_count = self.repetition_count.get(
            channel_id, ("", 0, 0)
        )
        if last_message == sentence:
            repetition_count += 1
        else:
            repetition_count = 0

        get_logger().debug(
            f"Repetition count for channel {channel_id} is {repetition_count}"
        )

        if self.should_throttle(repetition_count):
            get_logger().warning(
                "Repetition found, will throttle history for channel "
                + f"{channel_id} in next request"
            )
            throttle_message_id = response_message.id

        self.repetition_count[channel_id] = (
            sentence,
            throttle_message_id,
            repetition_count,
        )

    def should_throttle(self, repetition_count: int) -> bool:
        """
        Returns whether the bot should throttle history for a given repetition count
        """
        return repetition_count >= self.repetition_threshold

    def make_canonical(self, content: str) -> str:
        return content.strip().lower()
