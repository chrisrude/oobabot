# Contributing to Oobabot

## How can you contribute?

Find an [issue from our GitHub page](https://github.com/chrisrude/oobabot/issues), and mention that you'd like to work on it.  Let me know if you need any help getting started, I'm happy to help!

If the one you want to work on isn't there, please open an issue first so we can discuss it.  I'm happy to accept any contributions, but things will go more smoothly if we're on the same page before a lot of work is put in.  I want to help you be successful!

Read the stuff below, and then read the [development environment](#development-environment) section.  If you have any questions, please ask.  For contributions, please follow the [coding guidelines](#coding-guidelines).

## Architecture

Overall the design is pretty straightforward.  The bot connects to its dependent services: Oobabooga and possibly Stable Diffusion.  It then **logs into Discord** and waits for incoming messages.  When it finds a message it wants to respond to, it **generates a prompt** to Oobabooga, waits for a response, and then **posts that response** to Discord.  A similar pattern happens for Stable Diffusion, if it's enabled.

This description flows pretty similarly to how the code is structured.  Below I've broken down all the source files into the role they play.

### Important but Unexciting Parts

- `oobabot.py` - main, sets up and runs everything
- `ooba_client.py` - oobabooga client http API <> python
- `sd_client.py` - stable diffusion client http API <> python
- `settings.py` - reads user-customizable settings

### Bot Brains

- `discord_bot.py` - connects to Discord, monitors for messages, sends replies

- `bot_commands.py` - handles slash-commands from Discord
- `image_generator.py` - generates images and posts them, UI to redo images
- `decide_to_respond.py` - chooses which messages to reply to
- `prompt_generator.py` - generates the prompt sent to Oobabooga
- `repetition_tracker.py` - watches for bot loops and tries to stop them

### Utilities

- `http_client.py` - http client, used by both sd_client and ooba_client

- `response_stats.py` - logs operational stats
- `types.py` - defines generic versions messaging objects
- `templates.py` - creates all UI messages and bot prompts

Hopefully this will make things easier to understand!  This exact list of files may already be out of date by the time you read this, but hopefully this will give you some idea of where to look.

## Development Environment

tl;dr: Install Python 3.9+, [install poetry](https://python-poetry.org/docs/), clone the repo, run `poetry install`, run `poetry run oobabot`

```bash
sudo apt-get install python3 git curl

# install poetry (see https://python-poetry.org/docs/)
curl -sSL https://install.python-poetry.org | python3 -

# or whatever the poetry installer tells you to do
export PATH="~/.local/bin:$PATH"

# clone the repo and cd into it
git clone https://github.com/chrisrude/oobabot.git
cd oobabot

# this will build the project, downloading all dependencies
poetry install

# run it!
poetry run oobabot
```

You'll need a machine running Python 3.9 or higher, and [poetry](https://python-poetry.org/) installed.  Then just clone the repo.

Note: if you're using miniconda as your virtual environment, you'll need to explicitly add python to the environment before running `poetry install`.  See [the FAQ](FAQ.md) for more details.

Once you have the code checked out, you can install the dependencies with `poetry install`.  This will install all the dependencies, including the dev dependencies.

Running it is as simple as `poetry run oobabot`.

For it to do something interesting, you'll need a Discord account, and a bot token.  You can get one by following the instructions [here](https://discordpy.readthedocs.io/en/stable/discord.html).  Once you have a token, you can set it in your environment with `export DISCORD_TOKEN=your_token_here`.

For tests, you can run them with `poetry run pytest`.  This will run all the tests in the `tests` directory.  If you want to run a specific test, you can do so with `poetry run pytest tests/test_file.py::test_function`.  You can also run a specific test class with `poetry run pytest tests/test_file.py::TestClass`.

### Updating Dependencies

From time to time additonal dependencies will be added.  You can easily update your local environment with `poetry install`.  This will update all dependencies, including dev dependencies.

## Coding Guidelines

The project is built to support Python 3.9 and higher.  It uses [poetry](https://python-poetry.org/) to build and package with.  It uses [black](https://github.com/psf/black) for code formatting, with assistance from isort and flake8.  It uses [pytest](https://docs.pytest.org/en/stable/) for testing.

A lot of the code is based on the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).  I'm not religious about it, but I do try to follow it.  Generally, just try to match the style of whatever is already there.  Even if you would prefer different style choices, keeping things consistent is more important.  If you're not sure, ask!

## Submitting Your Pull Request

Before pushing, make sure you have pre-commit hooks enabled.  This will help you catch any simple issues before you push.  It will also automatically fix any formatting issues, so you don't have to micro that yourself.  You can install them with `poetry run pre-commit` as well as `poetry run pre-commit install`.

Once you've made your changes, you can submit a pull request.  I'll review it, and if everything looks good, I'll merge it in.  If there are any issues, I'll let you know and we can work through them together.

Thank you!
