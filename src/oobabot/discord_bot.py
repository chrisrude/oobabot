# Purpose: Discord client for Rosie
#

import discord
import re
import textwrap
import typing

from oobabot.fancy_logging import get_logger
from oobabot.ooba_client import OobaClient
from oobabot.response_stats import AggregateResponseStats


# only accept english keyboard characters in messages
# if other ones appear, they will be filtered out
FORBIDDEN_CHARACTERS = r'[^a-zA-Z0-9\-\\=\[\];,./~!@#$%^&*()_+{}|:"<>?` ]'
FORBIDDEN_CHARACTERS_PATTERN = re.compile(FORBIDDEN_CHARACTERS)


def sanitize_string(raw_string: str) -> str:
    '''
    Filter out any characters that are not commonly on a
    US-English keyboard
    '''
    return FORBIDDEN_CHARACTERS_PATTERN.sub('', raw_string)


def sanitize_message(raw_message: discord.Message) -> dict[str, str]:
    author = sanitize_string(raw_message.author.name)

    raw_guild = raw_message.guild
    if raw_guild:
        raw_guild_name = raw_guild.name
    else:
        raw_guild_name = 'DM'

    return {
        'author': author,
        'author_shortname': author.split('#')[0],
        'message_text': sanitize_string(raw_message.content).strip(),
        'server': sanitize_string(raw_guild_name),
    }


class PromptGenerator:
    def __init__(self, ai_name: str,
                 ai_persona: str,
                 ai_user_id: int):
        self.ai_name = ai_name
        self.ai_persona = ai_persona
        self.ai_user_id = ai_user_id

    async def generate_prompt(
            self,
            message_history: typing.AsyncIterator[discord.Message]) \
            -> str:
        '''
        Generates a prompt for the AI to use based on the message.
        '''

        prompt = textwrap.dedent(f'''
        You are in a chat room with multiple participants.
        Below is a transcript of recent messages in the conversation.
        Write the next message that you would send in this conversation,
        from the point of view of the participant named "{self.ai_name}".

        Here is some background information about "{self.ai_name}":
        {self.ai_persona}

        All responses you write must be from the point of view of
        {self.ai_name}, and plausible for {self.ai_name} to say in
        this conversation.  Do not continue the conversation as
        anyone other than {self.ai_name}.

        ### Transcript:

        ''')

        # message_history should be newer messages first,
        # so we reverse it to get older messages first
        history_lines = []
        async for raw_message in message_history:
            clean_message = sanitize_message(raw_message)

            author = clean_message["author"]
            if raw_message.author.id == self.ai_user_id:
                author = self.ai_name

            if clean_message["message_text"]:
                message_line = f'{author} says:\n' + \
                    f'{clean_message["message_text"]}\n\n'
                history_lines.append(message_line)

        prompt += '\n'.join(reversed(history_lines))
        prompt += f'{self.ai_name} says:\n'

        return prompt


class DiscordBot(discord.Client):
    HIST_SIZE = 10

    def __init__(self, ooba_client: OobaClient, ai_name: str,
                 ai_persona: str, wakewords: list[str]):
        self.ooba_client = ooba_client

        self.ai_name = ai_name
        self.ai_persona = ai_persona
        self.ai_user_id = -1
        self.wakewords = wakewords

        self.average_stats = AggregateResponseStats(ooba_client)

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

        if self.user:
            self.ai_user_id = self.user.id
            user_id_str = str(self.ai_user_id)
        else:
            user_id_str = '<unknown>'

        get_logger().info(
            f'Connected to discord as {self.user} (ID: {user_id_str})')
        get_logger().debug(
            f'monitoring DMs, plus {num_channels} channels across ' +
            f'{num_guilds} server(s)')

        get_logger().debug(f'AI name: {self.ai_name}')
        get_logger().debug(f'AI persona: {self.ai_persona}')

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

        clean_message = sanitize_message(raw_message)
        author = clean_message['author']
        server = clean_message['server']

        get_logger().debug(
            f'Request from {author} in server [{server}]')
        response_stats = self.average_stats.log_request_arrived()

        recent_messages = (raw_message.channel.history(limit=self.HIST_SIZE))

        generator = PromptGenerator(
            self.ai_name, self.ai_persona, self.ai_user_id)
        prompt = await generator.generate_prompt(recent_messages)

        try:
            async for sentence in self.ooba_client.request_by_sentence(
                prompt
            ):
                # print(sentence)

                # hack: filter out "oobabot says:" messages
                if f'{self.ai_name} says:' == sentence:
                    continue

                await raw_message.channel.send(sentence)
                response_stats.log_response_part()
        except Exception as err:
            get_logger().error(f'Error: {str(err)}')
            self.average_stats.log_response_failure()
            return

        response_stats.write_to_log(f"Response to {author} done!  ")
        self.average_stats.log_response_success(response_stats)
