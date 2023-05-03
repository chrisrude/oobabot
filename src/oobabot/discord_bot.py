# Purpose: Discord client for Rosie
#

import discord
import re

from oobabot.ooba_client import OobaClient
from oobabot.fancy_logging import get_logger
from oobabot.response_stats import ResponseStats


class DiscordBot(discord.Client):

    def __init__(self, ooba_client: OobaClient, wakewords: list[str]):
        self.ooba_client = ooba_client
        self.stats = ResponseStats(ooba_client)
        self.wakewords = wakewords

        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(intents=intents)

    async def on_ready(self):
        guilds = self.guilds
        num_guilds = len(guilds)
        num_channels = sum([len(guild.channels) for guild in guilds])

        get_logger().info(
            f'Connected to discord as {self.user} (ID: {self.user.id})')
        get_logger().debug(
            f'monitoring DMs, plus {num_channels} channels across {num_guilds} server(s)')
        get_logger().debug(
            f'wakewords: {", ".join(self.wakewords) if self.wakewords else "<none>"}'
        )

    def run(self, token):
        super().run(token)

    def should_reply_to_message(self, message):
        # we do not want the bot to reply to itself
        if message.author.id == self.user.id:
            return False

        # reply to all private messages
        if discord.ChannelType.private == message.channel.type:
            return True

        # reply to messages that include any `wakeword``, but not as part of
        # another word
        for wakeword in self.wakewords:
            if re.search(f'\\b{wakeword}\\b', message.content, re.IGNORECASE):
                return True

        # reply to all messages in which we're @-mentioned
        if self.user.id in [m.id for m in message.mentions]:
            return True

        # ignore anything else
        return False

    def log_stats(self):
        self.stats.write_stat_summary_to_log()

    async def on_message(self, message):
        if not self.should_reply_to_message(message):
            return

        get_logger().debug(
            f'Request from {message.author} in {message.channel}')
        self.stats.log_request_start()

        try:
            async for sentence in self.ooba_client.request_by_sentence(message.content):
                await message.channel.send(sentence)
                self.stats.log_response_part()
        except Exception as e:
            self.stats.log_response_failure(e)
            return

        log_prefix = f"Response to {message.author} done!  "
        self.stats.log_response_success(log_prefix)
