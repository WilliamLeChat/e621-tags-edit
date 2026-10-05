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
   images and animated GIFs. Videos use your Windows default player and need no
   extra Python library.
4. Edit `config.txt` and add your e621 username and API key. **KEEP THIS FILE**
   **PRIVATE; NEVER SHARE OR PUBLISH YOUR API KEY !!!**
5. Add at least one project to `tag_project.txt`. The app asks you to choose
   one when it starts.
6. Run the app:

   ```bash
   python main.py
   ```

   On Windows, `py main.py` can be used if `python` is not recognized.

## Using the app

1. Choose a project when the app starts. Its search and tag checkboxes are
   loaded automatically.
2. Review the post and click the checkboxes for the tags that apply.
3. Click **Submit** to add the selected tags to the post and continue. At least
   one tag must be selected.
4. Click **Skip** to move on without submitting tags. If you configured a set
   in `config.txt`, the skipped post is added to that set.
5. Use the page controls to browse other result pages, or **Change Project** to
   choose another project.
6. GIFs play in the app. For an MP4 or WebM post, click the preview to open the
   downloaded video with the default Windows app for that file type. The video
   is saved in the `video` folder beside `main.py`; the app creates this folder
   when needed. Install or choose a media player that supports the format if
   Windows asks which app to use. When you submit or skip and move to another
   post, the app automatically tries to delete the downloaded video. It also
   cleans it up when you browse away from the post or close the app. If another
   program is still using the video and Windows prevents deletion, the file may
   remain in the `video` folder and can be removed manually after closing the
   player. GIFs are animated in the app and are not saved in this folder.

### Keyboard shortcuts

- **1–9**: toggle the first through ninth tag checkbox. **0** toggles the
  tenth checkbox. The order matches the tags listed in the project's
  `[ADD_TAGS]` section.
- **Enter** (including the numeric keypad Enter): submit the selected tags.
- **Right Arrow**: skip the current post.
- **Left Arrow**: go back to the previous post on the current page.

Shortcuts work when focus is not in a text or page-number field. These keys
choose tag checkboxes; they do not choose a project.

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
