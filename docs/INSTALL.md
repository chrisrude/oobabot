
# Getting Started with Oobabot

To get this working, you'll need three things up and talking to each other:

## Fancy-Pants Architecture Diagram

Here's what you'll be setting up:

```none
    [ text-generation-webui ] <-- [ oobabot ] --> [ Discord's servers ]
    [        your pc        ]     [ your pc ]     [    the internet   ]
```

`[a]-->[b]` means: `a` connects to `b` via websockets

## 1. Install `text-generation-webui`

- get the text-generation-webui running on your box.  I used a few guides to do this:
  - [`u/Technical_Leather949`'s *How to install Llama 8bit and 4bit*](https://www.reddit.com/r/LocalLLaMA/comments/11o6o3f/how_to_install_llama_8bit_and_4bit/) on reddit
  - the instructions on [oobabooga's text-generation-webui github](https://github.com/oobabooga/text-generation-webui)

- download a model to run.

  I suspect the most interesting model will change frequenty, but as of May 3 20213 I am currently using [gpt4-x-alpaca, found on HuggingFace](https://huggingface.co/chavinlo/gpt4-x-alpaca).  This runs quite well a GPU with 10GB of RAM.
- enable the "API" plugin.  You can do this with the `--api` command-line option, or by enabling the "api" plugin onfrom the "interface mode" tab of the web UI.
- make note of the URL to the web UI, you'll need this in a later step (either ws:// or wss:// should work, your choice)

## 2. Create a Discord bot account for **`oobabot`**

You can follow the steps in [discord.py's documentation](https://discordpy.readthedocs.io/en/stable/discord.html),  [Discord's own documentation](https://discord.com/developers/docs/getting-started) or follow any number of online guides.
It boils down to first, creating a bot account:

- log into the discord web interface (the native apps don't expose these settings)
- go to the [application page](https://discord.com/developers/applications)
- create a new application.
- Choose a name that matches what you want the bot to be called.  This will be visible to users.
- Public bot / private bot doesn't matter
- generate a token for the bot.  MAKE NOTE OF THIS FOR LATER.
- enable the bot's intents as follows:
  - `PRESENCE INTENT: OFF`
  - `SERVER MEMBERS INTENT: ON`
  - `MESSAGE CONTENT INTENT: ON`

## 3. Invite **`oobabot`** to Discord servers

- go to the [application page](https://discord.com/developers/applications)
- click on your bot’s page, then the "OAuth2" tab
- under "Scopes" choose only "bot"
- Enable the following under "bot permissions":
  - **General Permissions**
    - ✅ read messages / view channels
    - *disable everything else*
  - **Text Permissions**
    - ✅ send messages
    - ✅ send messages in threads
    - ✅ read mention history
    - *disable everything else*
  - **Voice Permissions**
    - *disable everything*
- generate the URL
- give the URL to an admin on the Discord servers of interest, and have them accept the various warnings that will show up

## 4. Install oobabot itself

You can install oobabot on any machine that can reach the oobabooga's text-generation-webui URL you noted above.  By default it will assume it's the same machine, but you can also run it anywhere else if that's more convenient.

Using python3.8, 3.9 or 3.10, install the `oobabot` package from PiPy, using your favorite package manager.  E.g.

```bash
    pip install oobabot
```

## 5. Configure oobabot and have fun

Please refer to the [main README.md](../README.md) for setup instructions.

**`oobabot`** can be a lot of fun for a discord to talk to, especially with a creative personality.  Be creative and enjoy it!
