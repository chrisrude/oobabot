# `oobabot`

**`oobabot`** is a Discord bot which talks to a Large Language Model AIs (like LLaMA, llama.cpp, etc...), running on just about any api-enabled backend:

[oobabooga's text-generation-webui](https://github.com/oobabooga/text-generation-webui)

[TabbyAPI](https://github.com/theroyallab/tabbyAPI)

[aphrodite-engine](https://github.com/PygmalionAI/aphrodite-engine)

Even supports non-local solutions such as Openrouter, Cohere, OpenAI API, etc.


**updated! use `--generate-config` and update your configs!**


## Installation and Quick Start!
requires python 3.8+

```bash
  pip install git+https://github.com/jmoney7823956789378/oobabot
```

1. Install LLM loader with an OpenAI-compatible API.
     (optionally, skip this step and run via a cloud provider!
1. Create [a Discord bot account](https://discordpy.readthedocs.io/en/stable/discord.html), invite it to your server, and note its authentication token.
1. [Install **`oobabot`** (see INSTALL.md)](./docs/INSTALL.md)

```bash
~: pip install git+https://github.com/jmoney7823956789378/oobabot

~: oobabot --generate-config > config.yml

(This is the part where you open config.yml with you favorite text editor and fill in all the cool parts)

~: oobabot --generate-invite

(oobabot spits out a neat invite link for YOUR BOT!)

~: oobabot -c config.yml

2024-03-26 17:20:21,700  INFO Starting oobabot, core version 0.2.3

```

## Features

| **`oobabot`**  | how that's awesome |
|---------------|------------------|
| **user-supplied persona** | you supply the persona on how would like the bot to behave |
| **multiple conversations** | can track multiple conversational threads, and reply to each in a contextually appropriate way |
| **watchwords** | can monitor all channels in a server for one or more wakewords or @-mentions |
| **private conversations** | can chat with you 1:1 in a DM |
| **good Discord hygiene** | splits messages into independent sentences, pings the author in the first one |
| **low-latency** | streams the reply live, sentence by sentence.  Provides lower latency, especially on longer responses. |
| **stats** | track token generation speed, latency, failures and usage |
| **easy networking** | connects to discord from your machine using websockets, so no need to expose a server to the internet |
| **Stable Diffusion** | new in v0.1.4!  Optional image generation with AUTOMATIC1111 |
| **Slash Commands** | coming in v0.1.6... did your bot get confused?  `/lobotomize` it! |
| **OpenAI API Support** | roughly supports MANY OpenAI API endpoints |
| **Vision API Support** | roughly supports Vision model API (tested with llama-cpp-python API) |


You should now be able to run oobabot from wherever pip installed it.
If you're on windows, you should use `python3 -m oobabot (args here)`

There are a **LOT** of settings in the config.yaml, and it can be tough to figure out what works best.
I've included my very own (partially redacted) config here:
[config.yml file (sample)](./docs/config.sample.yml) here.


## Optional settings


- **`wakewords`**

   one or more words that the bot will look for.  It will reply to any message which contains one of these words, in any channel.

## Persona: the fun setting

- **`persona`**

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

Persona may be set from the command line with the **`--persona`** argument, or within the config.yml.

Alternatively, oobabot supports loading tavern-style json character cards!.

```
  # Path to a file containing a persona.  This can be just a single string, a json file in
  # the common "tavern" formats, or a yaml file in the Oobabooga format.  With a single
  # string, the persona will be set to that string.  Otherwise, the ai_name and persona will
  # be overwritten with the values in the file.  Also, the wakewords will be extended to
  # include the character's own name.
  #   default:
  persona_file: 
```

## Then, run it

You should see something like this if everything worked:

![oobabot running!](./docs/oobabot-cli.png "textually interesting image")

---

## Stable Diffusion via AUTOMATIC1111

- **`stable-diffusion-url`**

  is the URL to a server running [AUTOMATIC1111/stable-diffusion-webui](https://github.com/AUTOMATIC1111/stable-diffusion-webui)

  With it, users can ask **`oobabot`** to generate images and post the
  results to the channel.  The user who made the original request can
  choose to regenerate the image as they like.  If they either don't
  find one they like, or don't do anything within 3 minutes, the image
  will be removed.

  ![oobabot running!](./docs/zombietaytay.png "textually interesting image")

  Currently, detection of photo requests is very crude, and is only looking
  for messages which match this regex:

  ```python
        photowords = ["drawing", "photo", "pic", "picture", "image", "sketch"]
        self.photo_patterns = [
            re.compile(
                r"^.*\b" + photoword + r"\b[\s]*(of|with)?[\s]*[:]?(.*)$", re.IGNORECASE
            )
            for photoword in photowords
        ]
  ```

  Note that depending on the checkpoint loaded in Stable Diffusion, it may not be appropriate
  for your server's community.  I suggest reviewing [Discord's Terms of Service](https://discord.com/terms) and
  [Community Guidelines](https://discord.com/guidelines) before deciding what checkpoint to run.

  **`oobabot`** supports two different negative prompts, depending on whether the channel
  is marked as "Age-Restricted" or not.  This is to allow for more explicit content in
  channels which are marked as such.  While the negative prompt will discourage Stable
  Diffusion from generating an image which matches the prompt, but is not foolproof.

---

## Interacting with **`oobabot`**

By default, **`oobabot`** will listen for three types of messages in the servers it's connected to:

 1. any message in which **`oobabot`**'s account is @-mentioned
 1. any direct message
 1. any message containing a provided wakeword (see Optional Settings)

Also, the bot has a random chance of sending follow-up messages within the
same channel if others reply within 120 seconds of its last post. This "random chance" is configurable via the config.yaml:
```
Response chance vs. time - calibration table List of tuples with time in seconds and
response chance as float between 0-1
default: ['(180.0, 0.99)', '(300.0, 0.7)', '(600.0, 0.5)']
```
Here, you can see that NEW messages within 3 minutes of the bot's last reply will have a 99% chance of response.
Between 3-5 minutes, the default chance drops to 70%.
Between 5-10 minutes, the default chance drops to 50%.
Feel free to configure this to suit your needs! 
  

### Slash Commands

As of 0.1.6, the bot now supports slash commands:

| **`/command`**  | what it does |
|---------------|------------------|
| **`/lobotomize`** | make the bot forget everything in the channel before the command is run |
| **`/say "message"`** | speak as the bot |

Oobabot doesn't add any restrictions on who can run these commands, but luckily Discord does!  You can find this inside Discord by visiting "Server Settings" -> Integrations -> Bots and Apps -> hit the icon which looks like [/] next to your bot

If you're running on a large server, you may want to restrict who can run these commands.  I suggest creating a new role, and only allowing that role to run the commands.


## Contributing

Contributions are welcome!  Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for more information.
