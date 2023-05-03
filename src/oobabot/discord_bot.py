# Purpose: Discord client for Rosie
#

import discord
import re

from oobabot.fancy_logging import get_logger
from oobabot.ooba_client import OobaClient
from oobabot.response_stats import AggregateResponseStats


class DiscordBot(discord.Client):

    # only accept english keyboard characters in messages
    # if other ones appear, they will be filtered out
    FORBIDDEN_CHARACTERS = r'[^a-zA-Z0-9\-\\=\[\];,./~!@#$%^&*()_+{}|:"<>?` ]'

    def __init__(self, ooba_client: OobaClient, wakewords: list[str]):
        self.ooba_client = ooba_client
        self.average_stats = AggregateResponseStats(ooba_client)
        self.wakewords = wakewords

        self.forbidden_characters = re.compile(self.FORBIDDEN_CHARACTERS)

        # match messages that include any `wakeword`, but not as part of
        # another word
        self.wakeword_patterns = [
            re.compile(f'\\b{wakeword}\\b', re.IGNORECASE)
            for wakeword in wakewords
        ]

        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(intents=intents)

    async def on_ready(self) -> None:
        guilds = self.guilds
        num_guilds = len(guilds)
        num_channels = sum([len(guild.channels) for guild in guilds])

        user_id = self.user.id if self.user else "<unknown>"
        get_logger().info(
            f'Connected to discord as {self.user} (ID: {user_id})')
        get_logger().debug(
            f'monitoring DMs, plus {num_channels} channels across ' +
            f'{num_guilds} server(s)')

        str_wakewords = ", ".join(
            self.wakewords) if self.wakewords else "<none>"
        get_logger().debug(
            f'wakewords: {str_wakewords}'
        )

    def run(self, token: str) -> None:
        super().run(token)

    def should_reply_to_message(self, message: discord.Message) -> bool:
        # we do not want the bot to reply to itself
        if self.user and message.author.id == self.user.id:
            return False

        # reply to all private messages
        if discord.ChannelType.private == message.channel.type:
            return True

        # reply to all messages that include a wakeword
        for wakeword_pattern in self.wakeword_patterns:
            if wakeword_pattern.search(message.content):
                return True

        # reply to all messages in which we're @-mentioned
        if self.user and self.user.id in [m.id for m in message.mentions]:
            return True

        # ignore anything else
        return False

    def log_stats(self) -> None:
        self.average_stats.write_stat_summary_to_log()

    async def on_message(self, raw_message: discord.Message) -> None:
        if not self.should_reply_to_message(raw_message):
            return

        # filter out any characters that are not in the english keyboard
        author = self.forbidden_characters.sub(
            '', str(raw_message.author))

        author_shortname = author.split('#')[0]

        message = self.forbidden_characters.sub(
            '', raw_message.content)

        channel = self.forbidden_characters.sub(
            '', str(raw_message.channel))

        server = self.forbidden_characters.sub(
            '', str(raw_message.guild))

        get_logger().debug(
            f'Request from {author} in [{server}][#{channel}]')
        response_stats = self.average_stats.log_request_arrived()

        prefix2 = "\nThe following request has been made by a user "
        prefix2 += f"named {author_shortname}.  "
        prefix2 += "They are your friend.\n\n"

        try:
            async for sentence in self.ooba_client.request_by_sentence(
                message, prefix2=prefix2
            ):
                await raw_message.channel.send(sentence)
                response_stats.log_response_part()
        except Exception as err:
            get_logger().error(f'Error: {str(err)}')
            self.average_stats.log_response_failure()
            return

        response_stats.write_to_log(f"Response to {author} done!  ")
        self.average_stats.log_response_success(response_stats)
