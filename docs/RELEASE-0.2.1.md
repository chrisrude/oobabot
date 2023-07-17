
# Release v.0.2.1

## What's Changed

True to the version, his is a small bug-fix release.  I had been wanting to get a few more small features in, but a few urgent bugs came up, and I wanted to get them out to users as soon as possible.  My priority is to make sure things keep working well first, before adding new features.

## New Contributors

This is the first release to feature pull requests from the community!  Thanks to everyone who took the time out to make `oobabot` better!

* @clintkittiesmeow (with help from @jmoney7823956789378) made their first contribution in [PR 61](https://github.com/chrisrude/oobabot/pull/61)
* @harlyh made their first contribution in [PR 66](https://github.com/chrisrude/oobabot/pull/66)

## New Features

* Stable Diffusion Parameters in Prompt by @clintkittiesmeow

A discord user, with your permission, can now customize pretty much any aspect of Stable Diffusion generation within the prompt.  For example:

```none
   Make me a picture of a cat wearing a hat width=512 height=512 steps=10 seed=10
```

The syntax is just `<param>=<value>` and you can include as many as you want.

A parameter must pass two checks before they are passed to Stable Diffusion:

* It must be included in the new `user_override_params` setting
* It must have a default in the `request_params` dictionary.  We use this to know the type of the parameter, and to provide a default value if the user doesn't specify one.

The new yaml setting for `user_override_params` looks like this, and will enable these settings by default:

```yaml
  # These parameters can be overridden by the Discord user by including them in their image
  # generation request.  The format for this is: param_name=value  This is a whitelist of
  # parameters that can be overridden. They must be simple parameters (strings, numbers,
  # booleans), and they must be in the request_params dictionary.  The value the user inputs
  # will be checked against the type from the request_params dictionary, and if it doesn't
  # match, the default value will be used instead.  Otherwise, this value will be passed
  # through to Stable Diffusion without any changes, so be mindful of what you allow here.
  # It could potentially be used to inject malicious values into your SD server.  For
  # example, steps=1000000 could be bad for your server.
  user_override_params:
    - cfg_scale
    - enable_hr
    - model
    - negative_prompt
    - sampler_name
    - seed
    - height
    - width
```

Thanks to @jmoney7823956789378 and @clintkittiesmeow for the idea and the initial implementation!  It would not have happened without you. :)

## Bug Fixes / Tech Improvements

* Fixed the Unicode logging issue in ooba_client.py

A Windows 11 update has reportedly caused an issue with the `--log-all-the-things` parameter.  This fix should resolve that issue.  Thanks @harlyh for the quick fix.

* Fixed an urgent bug with streaming responses

When using streaming responses, the bot would not be able to see its own messages in the history.  This was due to a mistake in how the messages were edited when updates came in.  This is now fixed.

* Removed the ai-generated keywords feature, which was never finished and didn't really work right.  It would cause issues with the new Stable Diffusion keyword parsing, so it's better to just remove it for now.

### Full Changelog

[All changes from 0.2.0 to 0.2.1](https://github.com/chrisrude/oobabot/compare/v0.2.0...v0.2.1)
