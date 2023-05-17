# Release v.0.1.7

## New Features

- **Configure All the Things**

  You can now configure every setting passed to Oobabooga
  and Stable Diffusion, and more, via a config.yml file.

- **Streaming Responses**

  That's right!  It's a little janky, but you can now have the
  bot stream its response into a single message.  Just pass
  the `--stream-responses` flag, or enable the `stream_responses`
  flag in the config.yml file.

  This works by continuously editing the bot's response message.

- **Stop Markers**

  Some models were generating tokens that were appearing in the chat
  output.  There is a new config setting, `stop_markers`.  We'll watch
  the response for these markers, and if we see any one on its own line
  we'll stop responding.

```yaml
  # A list of strings that will cause the bot to stop generating a response when
  # encountered.
  #   default: ['### end of transcript ###<|endoftext|>', '<|endoftext|>']
  stop_markers:
    - '### End of Transcript ###<|endoftext|>'
    - <|endoftext|>
```

- **Extra Prompt Text** for Stable Diffusion

  You can now add extra prompt text to every prompt sent to Stable Diffusion.

  This could help customize the image generation to be more appropriate for
  your character's persona, or influence the type of images generated in ways
  that are more subtle than allowed by other settings.

  To use it, generate or regenerate the config.yml file and then set

```yaml
  # This will be appended to every image generation prompt sent to Stable Diffusion.
  #   default:
  extra_prompt_text: "as a tattoo"
```

in the `stable_diffusion:` section.

## Breaking Changes

The following command line arguments have been deprecated:

- `diffusion_steps`
- `image_height`
- `image_width`
- `stable_diffusion_sampler`
- `sd_negative_prompt`
- `sd_negative_prompt_nsfw`

They're deprecated because they're more naturally included in the
`stable_diffusion: request_params:` section in the new config file, and it would be
confusing to have the same setting in two places.

I'll keep them around for a while, but they will be removed in a
future release.

If you were generating a new config file anyway, then there's no
impact to you.

## New Feature Q&A

### What is in the new config file?

You can now configure **every parameter** sent to Oobabooga
and Stable Diffusion to generate responses.  Some notable ones are:

- truncation_length (aka "max tokens")
- temperature (controls bot creativitiy)
- repetition_penalty
- early_stopping flag

In addition, this is done in a way so that anything in the
sections is just "passed through" to the underlying service.

This means that if a new release of Oobabooga or Stable Diffusion
adds a new parameter, you can just add it to the config.yml,
without needing a software update.

### Creating a new `config.yml` file

Pass `--generate-config` to the CLI to print a fesh new config.yml
file to sdout.  You can then redirect this to a file.

This file will include any other settings you've supplied on the
command line.  So if you're upgrading from an earlier version,
all you have to do is:

If you've been running with the CLI alone, all you need to do is:
  `oobabot {your normal args} --generate-config > config.yml`

and then
  `oobabot`

## Where to place `config.yml`

`oobabot` will look for a config.yml file in the current
directory by default.  If you want to place it somewhere
else, you can specify a different location with the
`--config-file` flag.  e.g.

```bash
   oobabot --config-file /path/to/config.yml
```

### Upgrading from an earlier version

If you ever upgrade and want to regenerate the config.yml,
you can just do this:

  `oobabot --generate-config > config.yml`

Your previous config.yml file will be read before generating the new one,
and the new one will include all the settings from the old one, plus
any new settings that have been added since the last time you generated
the config.yml file.

### Notes on Streaming Response Jankeyness

It's janky in the following ways:

- there are rate limits on how fast edits can be made,
  so it's not silky smooth.  We will wait at least 0.2 seconds
  between edits, but it may be longer.  The actual speed will depend
  on how fast Discord allows edits.

- you'll see an "edited" tag on the message.  But if you can
  ignore that, that's cool.

- you won't be notified when the bot responds this way.  This is
  because Discord sends new message notifications immediately
  on message send, so the notification would only contain a single
  token.  This would be annoying, so we don't do it.

I'm just impressed it works at all.

## Bug Fixes / Tech Improvements

- Fixed an issue with an "image regeneration failed"
  when regenerating images against SD servers which took more than 5
  seconds to render

- Fixed an issue where regenerating an image while simultaneously
  the bot was generating a second reply in the channel would cause
  an "image regeneration failed" error, sometimes.

- improve heuristic for detecting our own image posts.  Sometimes
  the bot would pick up on the UI elements of its own image posts.
  This should be fixed now.

- Do a better job at logging exceptions that happen during
  message responses

- new over-engineered config file parsing, should afford
  easier paramater adding in the future

- fixes for pylint, added to precommit hooks

### Full Changelog

https://github.com/chrisrude/oobabot/compare/v0.1.6...v0.1.7
