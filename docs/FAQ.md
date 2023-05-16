# FAQ

## How do I

### Q. ... limit the bot to certain channels?

A. You can do this!  This change is made on the Discord server side, though it's a bit hidden.  Here are the current steps:

- In your server, right-click on the channel you want to limit access to
- Choose "Edit Channel", then "Permissions"
- If this is a public channel, you'll need to click "Advanced Permissions"
- If you look for your bot's name, you should see both a Role and a Member with the bot's name.
- Click on the Role, and then click the "X" next to "View Channel" to remove that permission.
- Do the same for the bot's account (the one with the #0000)
- Click "save changes" at the bottom

### Q. ... I'm seeing an error like `"File "", line 1004, in _find_and_load_unlocked"` when using miniconda

A. This is a known issue with miniconda.  For some reason, poetry gets super-confused unless you explicitly add python to the virtual environment before poetry does its thing.

To fix this, delete the conda environment, then recreate it with:
  `conda create -n oobabot python=3.10`

Then proceed with `poetry install`, etc.
