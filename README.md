# `oobabot`

**`oobabot`** is a Discord bot which talks to a Large Language Model AIs (like LLaMA, llama.cpp, etc...), running on [oobabooga's text-generation-webui](https://github.com/oobabooga/text-generation-webui).

[![python lint and test with poetry](https://github.com/chrisrude/oobabot/actions/workflows/python-package.yml/badge.svg)](https://github.com/chrisrude/oobabot/actions/workflows/python-package.yml)

## Installation

```bash
  pip install oobabot
```

requires python 3.8+

## Usage

```bash
$ oobabot --wakewords rosie cat --ai-name Rosie --persona "you are a cat named Rosie"

2023-05-04 00:24:10,968 DEBUG Oobabooga base URL: ws://localhost:5005
2023-05-04 00:24:11,133 INFO Connected to Oobabooga!
2023-05-04 00:24:11,133 DEBUG Connecting to Discord...
2023-05-04 00:24:13,807 INFO Connected to discord as RosieAI#0000 (ID: 1100100011101010101)
2023-05-04 00:24:13,807 DEBUG monitoring DMs, plus 24 channels across 1 server(s)
2023-05-04 00:24:13,807 DEBUG AI name: Rosie
2023-05-04 00:24:13,807 DEBUG AI persona: you are a cat named Rosie
2023-05-04 00:24:13,807 DEBUG wakewords: rosie, cat
```

See below for more details on the command line options.

## Motivation

![oobabot in action!](./docs/oobabot.png "discord action shot")

Text-generative UIs are cool to run at home, and Discord is fun to mess with your friends.  Why not combine the two and have something awesome!

Real motivation: I wanted a chatbot in my discord that would act like my cat.  A "catbot" if you will.

## Features

| **`oobabot`**  | how that's awesome |
|---------------|------------------|
| **user-supplied persona** | you supply the persona on how would like the bot to behave |
| **multiple converations** | can track multiple conversational threads, and reply to each in a contextually appropriate way |
| **watchwords** | can monitor all channels in a server for one or more wakewords or @-mentions |
| **private conversations** | can chat with you 1:1 in a DM |
| **good Discord hygiene** | splits messages into independent sentences, pings the author in the first one |
| **low-latency** | streams the reply live, sentence by sentence.  Provides lower latency, especially on longer responses. |
| **stats** | track token generation speed, latency, failures and usage |
| **easy networking** | connects to discord from your machine using websockets, so no need to expose a server to the internet |

## Getting Started with **`oobabot`**

### See the [Installation Guide](./docs/INSTALL.md) for step-by-step instructions

## Installation tl;dr

1. Install [oobabooga's text-generation-webui](https://github.com/oobabooga/text-generation-webui) and enable its API module
1. Create [a Discord bot account](https://discordpy.readthedocs.io/en/stable/discord.html), invite it to your server, and note its authentication token.
1. [Install **`oobabot`** (see INSTALL.md)](./docs/INSTALL.md)

```bash
~: pip install oobabot

~: export DISCORD_TOKEN = __your_bots_discord_token__

~: oobabot --base-url ws://oobabooga-hostname:5005/ --ai-name YourBotsName --persona "You are a cat named YourBotsName"
```

You should now be able to run oobabot from wherever pip installed it.

```none
usage: oobabot [-h] [--base-url BASE_URL] [--ai-name AI_NAME] [--wakewords [WAKEWORDS ...]]
               [--persona PERSONA] [--local-repl] [--log-all-the-things LOG_ALL_THE_THINGS]

Discord bot for oobabooga's text-generation-webui

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   Base URL for the oobabooga instance. This should be ws://hostname[:port] for
                        plain websocket connections, or wss://hostname[:port] for websocket
                        connections over TLS.
  --ai-name AI_NAME     Name of the AI to use for requests. This can be whatever you want, but might
                        make sense to be the name of the bot in Discord.
  --wakewords [WAKEWORDS ...]
                        One or more words that the bot will listen for. The bot will listen in all
                        discord channels can access for one of these words to be mentioned, then
                        reply to any messages it sees with a matching word. The bot will always reply
                        to @-mentions and direct messages, even if no wakewords are supplied.
  --persona PERSONA     This prefix will be added in front of every user-supplied request. This is
                        useful for setting up a 'character' for the bot to play. Alternatively, this
                        can be set with the OOBABOT_PERSONA environment variable.
  --local-repl          start a local REPL, instead of connecting to Discord
  --log-all-the-things LOG_ALL_THE_THINGS
                        prints all oobabooga requests and responses in their entirety to STDOUT

Also, to authenticate to Discord, you must set the environment variable: DISCORD_TOKEN = <your bot's
discord token>
```

## Required settings

- **`DISCORD_TOKEN`** environment variable

   Set your shell environment's **`DISCORD_TOKEN`** to token Discord provided when you set up the bot account.  It should be something like a 72-character-long random-looking string.

    **bash example**

    ``` bash
    export DISCORD_TOKEN=___YOUR_TOKEN___
    ```

    **fish example**

    ``` fish
    set -Ux DISCORD_TOKEN ___YOUR_TOKEN___
    ```

- **`--base-url`**

    The base URL of oobabooga's streaming web API.  This is
    required if the oobabooga machine is different than where you're running **`oobabot`**.

    By default, this will be port 5005 (even though the HTML UI runs on a different port).  The protocol should typically be ws://.

    All together, this should look something like:

    ```bash
    --base-url ws://localhost:5005
    ```

   This is also the default value, but any other setting should follow the same form.

## Optional settings

- **`--ai-name`**

   the name the AI will be instructed to call itself.  Note that this technically doesn't need to be the same as the bot in your discord, but it would likely make sense to your users if they are at least similar.

- **`--wakewords`**

   one or more words that the bot will look for.  It will reply to any message which contains one of these words, in any channel.

- **`--local-repl`**

    instead of connecting to discord, just start up a local REPL and send these prompts directly to the oobabooga server.  Useful if you want to test if that part is working in isolation.  Note that in this mode you will be sending the oobabooga server raw input, and so the persona or AI name settings will be ignored.

## Persona: the fun setting

- **`--persona`**

    is a short few sentences describing the role your bot should act as.  For instance, this is the setting I'm using for my cat-bot, whose name is "Rosie".

```console
Here is some background information about Rosie:
- You are Rosie
- You are a cat
- Rosie is a female cat
- Rosie is owned by Chris, whose nickname is xxxxxxx
- Rosie loves Chris more than anything
- You are 9 years old
- You enjoy laying on laps and murder
- Your personality is both witty and profane
- The people in this chat room are your friends
```

Persona may be set from the command line with the **`--persona`** argument.

Alternatively, it can be set through the environment variable **`OOBABOT_PERSONA`**.

## Then, run it

You should see something like this if everything worked:

![oobabot running!](./docs/oobabot-cli.png "textually interesting image")

---

## Interacting with **`oobabot`**

By default, **`oobabot`** will listen for three types of messages in the servers it's connected to:

 1. any message in which **`oobabot`**'s account is @-mentioned
 1. any direct message
 1. any message containing a provided wakeword (see Optional Settings)

Also, the bot has a random chance of sending follow-up messages within the
same channel if others reply within 120 seconds of its last post.  The exact
parameters for this are in flux, but is meant to simulate a natural conversation
flow, without forcing others to always post a wakeword.

## Known Issues

- ooba's text generation can error with OOM when more than one request comes in at once.
- sometimes the bot wants to continue conversations on behalf of other members of the chatroom.  I have some hacks in place to notice and truncate this behavior, but it can lead to terse responses on occasion.
- found one not listed here?  [Create an issue](https://github.com/chrisrude/oobabot/issues) on github!
