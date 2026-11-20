# TODO

This file tracks existing features and possible improvements. Checked items
are implemented; unchecked items are ideas to prioritize or complete.

## Implemented features

### 1. Installation and configuration

- [x] Install the `requests` and `Pillow` dependencies.
- [x] Load the e621 account, API key, and User-Agent from
  `config/config.txt`.
- [x] Define multiple search projects in `config/tag_project.txt`.
- [x] Select a project at startup or change it from the main window.
- [x] Optionally combine two projects' search terms and add-tags at startup or
  when changing projects.
- [x] Add tags from `config/default_tag.txt` to every project's search.
- [x] Exclude tags listed in `config/Blacklist.txt` from search results.
- [x] Optionally use an e621 set to exclude previously skipped posts and add
  skipped posts to that set.

### 2. Searching and navigation

- [x] Search e621 posts using the project's filters and configured result
  limit.
- [x] Browse result pages, enter a page number directly, and navigate to the
  previous or next page.
- [x] Display the current post's ID and tags, along with the tags available for
  the selected project.

### 3. Reviewing and acting on posts

- [x] Select tags to add and submit the changes to e621.
- [x] Prevent submission when no tags are selected.
- [x] Skip a post without changing its tags and, if a set is configured, add
  the post to that set.
- [x] Add or remove the current post from e621 favorites using the star button
  or the `F` key; show an outlined or filled star and confirm the result.
- [x] Reload the current post's media.

### 4. Media display

- [x] Download and display images and animated GIFs in the application.
- [x] Download MP4 and WebM videos and open them with the default Windows
  player.
- [x] Open images in full screen, zoom with the mouse wheel, and drag to pan.
- [x] Delete temporary video files when leaving a post or closing the
  application.

### 5. Interface and status

- [x] Switch between light and dark themes.
- [x] Display the hourly tag-edit quota and refresh it periodically after
  changes.
- [x] Display the elapsed time since the application started.
- [x] Show loading, success, and error statuses in the interface.
- [x] Run API requests and media loading in the background to keep the
  interface responsive.

### 6. Keyboard shortcuts

- [x] `1` through `9`: toggle the first nine tag checkboxes; `0`: toggle the
  tenth.
- [x] `Enter`: submit the selected tags.
- [x] Right Arrow: skip the current post.
- [x] Left Arrow: return to the previous post on the current page.
- [x] `R`: reload the current post's media.
- [x] `F`: add or remove the current post from favorites.
- [x] Ignore action shortcuts when focus is in a text field.

### 7. Documentation

- [x] Document installation, usage, shortcuts, and configuration files in
  `README.md`.
- [x] Document known errors and troubleshooting in `docs/ERROR.md`.

### 8. Current e621 API compatibility

- [x] Accept post responses using the current top-level list format and the
  previous `{"posts": [...]}` format.
- [x] Support both list-based and category-based tag data.
- [x] Load original, sample, and preview media URLs from the current e621 file
  structure.
- [x] Preserve media extension detection and tag submission with older API
  response formats.

## To Do
