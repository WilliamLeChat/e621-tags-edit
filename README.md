# e621 Tag Editor

A small desktop app for reviewing e621 posts and submitting tags.

## Setup

1. Install Python 3 and make sure Tkinter is available.
2. Open a terminal in this folder.
3. Install the required libraries:

   ```bash
   python -m pip install -r requirements.txt
   ```

   This installs `requests` for e621 API requests and `Pillow` for displaying
   images.
4. Edit `config.txt` and add your e621 username and API key. Keep this file
   private; never share or publish your API key.
5. Add at least one project to `tag_project.txt`. The app asks you to choose
   one when it starts.
6. Run the app:

   ```bash
   python main.py
   ```

   On Windows, `py main.py` can be used if `python` is not recognized.

## Text files

### `config.txt` — account and current settings

Fill in your own e621 account details. Keep the section names and `key=value`
format. You do not need to fill in `[SEARCH]` or `[ADD_TAGS]` yourself: when
you choose a project at startup, the app copies those settings from
`tag_project.txt` into `config.txt`.

```ini
[API]
username=YOUR_E621_USERNAME
api_key=YOUR_E621_API_KEY
user_agent=e621 Tag Editor by YOUR_USERNAME

[SET]
your_existing_set_shortname
```

`username` and `api_key` are required. Use a descriptive `user_agent`, as
required by e621. `SET` is optional; if set, it must be the shortname of an
existing e621 set. Skipped posts are added to that set and excluded from later
searches.

The selected project's `[SEARCH]` and `[ADD_TAGS]` settings are copied from
`tag_project.txt` into `config.txt` automatically at startup.

### `tag_project.txt` — selectable projects

Add one or more projects. Each project needs a name and can have its own search
and checkbox tags:

```text
[NAME]
Knots on Canine Penises
[SEARCH]
tags=canine_penis -knotted_penis
limit=75
[ADD_TAGS]
knotted_penis
knot
```

Repeat these sections for each project. Search options use e621's search
syntax; put the search terms after `tags=`. `limit` is the maximum number of
posts requested on each page. For example, `limit=75` requests up to 75 posts
per page; use the page controls in the app to browse more results. The project
name is shown in the startup selection window.

### `default_tag.txt` — tags added to every project's search

Put one e621 search tag on each line:

```text
status:active
-animated
```

These terms are added to the selected project's search, so they apply to every
project. Lines starting with `#` are ignored.

### `Blacklist.txt` — tags to exclude from searches

Put one tag on each line:

```text
gore
scatplay
```

The app excludes these tags from search results. Blank lines and lines starting
with `#` are ignored.

### `requirements.txt` — Python libraries

This file lists the libraries installed in step 3. You normally do not need to
edit it; add a library here only if the app gains a new dependency.
