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
    '''
    Purpose: generate a prompt for the AI to use, given
    the message history and persona.
    '''

    # this is set by the AI, and is the maximum length
    # it will understand before it starts to ignore
    # the rest of the prompt
    MAX_PROMPT_LEN = 2048

    def __init__(self, ai_name: str,
                 ai_persona: str):
        self.ai_name = ai_name
        self.ai_persona = ai_persona

    async def generate_prompt(
            self,
            ai_user_id: int,
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
            if raw_message.author.id == ai_user_id:
                author = self.ai_name

            if clean_message["message_text"]:
                message_line = f'{author} says:\n' + \
                    f'{clean_message["message_text"]}\n\n'
                history_lines.append(message_line)

        # put this at the very end to tell the UI what it
        # should complete.  But generate this now so we
        # know how long it is.
        prompt_footer = f'{self.ai_name} says:\n'

        # add on more history, but only if we have room
        # if we don't have room, we'll just truncate the history
        # by discarding the oldest messages first
        # this is s
        # it will understand before ignore
        #
        prompt_len_remaining = self.MAX_PROMPT_LEN - \
            len(prompt) - len(prompt_footer)

        added_history = 0
        for next_line in history_lines.pop():
            if len(next_line) > prompt_len_remaining:
                get_logger().warn(
                    'prompt too long, truncating history.  ' +
                    f'added {added_history} lines, dropped ' +
                    f'{len(history_lines)} lines'
                )
                break
            added_history += 1
            prompt += next_line

        prompt += prompt_footer

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
        self.prompt_generator = PromptGenerator(ai_name, ai_persona)

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
        try:
            await self.send_response(raw_message)
        except Exception as e:
            get_logger().error(
                f'Exception while sending response: {e}', exc_info=True)

    async def send_response(self, raw_message: discord.Message) -> None:
        clean_message = sanitize_message(raw_message)
        author = clean_message['author']
        server = clean_message['server']
        get_logger().debug(
            f'Request from {author} in server [{server}]')

        recent_messages = (raw_message.channel.history(limit=self.HIST_SIZE))

        prompt = await self.prompt_generator.generate_prompt(
            self.ai_user_id, recent_messages)

        response_stats = self.average_stats.log_request_arrived(prompt)

        try:
            async for sentence in self.ooba_client.request_by_sentence(
                prompt
            ):
                # print(sentence)

                # if the AI gives itself a second line, just ignore
                # the line instruction and continue
                if f'{self.ai_name} says:' == sentence:
                    get_logger().warning(
                        f'Filtered out "{sentence}" from response, continuing'
                    )
                    continue

                # hack: abort response if it looks like the AI is
                # continuing the conversation as someone else
                if sentence.endswith(' says:'):
                    get_logger().warning(
                        f'Filtered out "{sentence}" from response, aborting'
                    )
                    break

                await raw_message.channel.send(sentence)
                response_stats.log_response_part()
        except Exception as err:
            get_logger().error(f'Error: {str(err)}')
            self.average_stats.log_response_failure()
            return

        response_stats.write_to_log(f"Response to {author} done!  ")
        self.average_stats.log_response_success(response_stats)
