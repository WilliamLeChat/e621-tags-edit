import io
import logging
import os
import queue
import re
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import urlparse
import requests
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageTk

BASE_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIRECTORY = os.path.join(BASE_DIRECTORY, "config")
CONFIG_FILE = os.path.join(CONFIG_DIRECTORY, "config.txt")
TAG_PROJECT_FILE = os.path.join(CONFIG_DIRECTORY, "tag_project.txt")
DEFAULT_TAG_FILE = os.path.join(CONFIG_DIRECTORY, "default_tag.txt")
BASE_URL = "https://e621.net"
BLACKLIST_FILE = os.path.join(CONFIG_DIRECTORY, "Blacklist.txt")
TAG_EDIT_QUOTA_REFRESH_INTERVAL = 15
VIDEO_EXTENSIONS = {".mp4", ".webm"}
VIDEO_DIRECTORY = os.path.join(BASE_DIRECTORY, "video")


def parse_remaining_tag_edits(page_html):
    text_parts = []

    class PageTextParser(HTMLParser):
        def handle_data(self, data):
            text_parts.append(data)

    parser = PageTextParser()
    parser.feed(page_html)
    page_text = " ".join(text_parts)
    match = re.search(
        r"Remaining hourly tag edits:\s*(-?\d+)",
        page_text
    )
    if match is None:
        raise RuntimeError(
            "Could not find the tag edit quota on the e621 page."
        )
    return int(match.group(1))


class Config:

    def __init__(self):
        self.username = ""
        self.api_key = ""
        self.search_tags = ""
        self.add_tags = []
        self.set_shortname = ""
        self.user_agent = "e621-tag-editor/1.0"
        self.limit = 50


def load_config():

    cfg = Config()
    section = None

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if line.startswith("[") and line.endswith("]"):
                    section = line
                    continue

                if section == "[API]":
                    if line.startswith("username="):
                        cfg.username = line.split("=", 1)[1].strip()
                    elif line.startswith("api_key="):
                        cfg.api_key = line.split("=", 1)[1].strip()
                    elif line.startswith("user_agent="):
                        cfg.user_agent = line.split("=", 1)[1].strip()

                elif section == "[SEARCH]":
                    if line.startswith("tags="):
                        cfg.search_tags = line.split("=", 1)[1].strip()
                    elif line.startswith("limit="):
                        try:
                            cfg.limit = int(line.split("=", 1)[1].strip())
                        except ValueError:
                            cfg.limit = 50

                elif section == "[ADD_TAGS]":
                    cfg.add_tags.append(line)

                elif section == "[SET]":
                    cfg.set_shortname = line
    except FileNotFoundError:
        raise RuntimeError(f"Configuration file not found: {CONFIG_FILE}")

    return cfg


def load_tag_projects():
    projects = []
    current_project = None
    section = None

    try:
        with open(TAG_PROJECT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                value = line.strip()
                if value.startswith("[") and value.endswith("]"):
                    if value == "[NAME]":
                        if current_project is not None:
                            projects.append(current_project)
                        current_project = {
                            "name": "",
                            "search": [],
                            "add_tags": []
                        }
                    section = value
                    continue

                if current_project is None or not value or value.startswith("#"):
                    continue
                if set(value) == {"-"}:
                    continue

                if section == "[NAME]" and not current_project["name"]:
                    current_project["name"] = value
                elif section == "[SEARCH]":
                    current_project["search"].append(value)
                elif section == "[ADD_TAGS]":
                    current_project["add_tags"].append(value)
    except FileNotFoundError:
        raise RuntimeError(f"Projects file not found: {TAG_PROJECT_FILE}")

    if current_project is not None:
        projects.append(current_project)

    projects = [
        project for project in projects
        if project["search"] or project["add_tags"]
    ]
    for index, project in enumerate(projects, start=1):
        if not project["name"]:
            search_tags = next(
                (
                    line.split("=", 1)[1].strip()
                    for line in project["search"]
                    if line.startswith("tags=")
                ),
                ""
            )
            if search_tags:
                label = search_tags[:40]
                if len(search_tags) > 40:
                    label += "..."
                project["name"] = f"Project {index}: {label}"
            else:
                project["name"] = f"Unnamed project {index}"

    return projects


def load_default_search_tags():
    try:
        with open(DEFAULT_TAG_FILE, "r", encoding="utf-8") as f:
            return [
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]
    except FileNotFoundError:
        raise RuntimeError(f"Default tags file not found: {DEFAULT_TAG_FILE}")


def add_default_search_tags(project, default_tags):
    updated_project = {
        **project,
        "search": list(project["search"])
    }
    default_query = " ".join(default_tags)
    if not default_query:
        return updated_project

    for index, line in enumerate(updated_project["search"]):
        if line.startswith("tags="):
            current_query = line.split("=", 1)[1].strip()
            default_tag_set = set(default_tags)
            current_terms = []
            seen_default_tags = set()
            for term in current_query.split():
                if term in default_tag_set:
                    if term in seen_default_tags:
                        continue
                    seen_default_tags.add(term)
                current_terms.append(term)
            missing_tags = [
                tag for tag in default_tags
                if tag not in seen_default_tags
            ]
            normalized_query = " ".join(current_terms + missing_tags)
            if normalized_query != current_query:
                updated_project["search"][index] = (
                    f"tags={normalized_query}"
                )
            break
    else:
        updated_project["search"].insert(0, f"tags={default_query}")

    return updated_project


def replace_config_sections(config_text, project):
    replacements = {
        "[SEARCH]": project["search"],
        "[ADD_TAGS]": project["add_tags"]
    }
    output = []
    replaced = set()
    skipping_section = False

    for line in config_text.splitlines():
        value = line.strip()
        if value.startswith("[") and value.endswith("]"):
            skipping_section = value in replacements
            if skipping_section:
                if value not in replaced:
                    output.append(value)
                    output.extend(replacements[value])
                    replaced.add(value)
            else:
                output.append(line)
            continue

        if not skipping_section:
            output.append(line)

    for section, lines in replacements.items():
        if section not in replaced:
            if output and output[-1]:
                output.append("")
            output.append(section)
            output.extend(lines)

    return "\n".join(output) + "\n"


def apply_tag_project(project):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config_text = f.read()
    except FileNotFoundError:
        raise RuntimeError(f"Configuration file not found: {CONFIG_FILE}")

    updated_config = replace_config_sections(config_text, project)
    with open(CONFIG_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated_config)


def choose_tag_project(root, projects):
    selection = {"project": None}
    dialog = tk.Toplevel(root)
    dialog.title("Select a tag project")
    dialog.resizable(False, False)
    tk.Label(dialog, text="Which tag project do you want to use?").pack(
        padx=12, pady=(12, 6)
    )

    project_list = tk.Listbox(dialog, width=45, height=min(len(projects), 12))
    for project in projects:
        project_list.insert(tk.END, project["name"])
    project_list.pack(padx=12, pady=6)
    project_list.selection_set(0)
    project_list.activate(0)

    def confirm_selection(event=None):
        selected = project_list.curselection()
        if selected:
            selection["project"] = projects[selected[0]]
            dialog.destroy()

    button_frame = tk.Frame(dialog)
    button_frame.pack(pady=(4, 12))
    tk.Button(button_frame, text="Select", command=confirm_selection).pack(
        side="left", padx=5
    )
    tk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(
        side="left", padx=5
    )
    project_list.bind("<Double-Button-1>", confirm_selection)
    dialog.bind("<Return>", confirm_selection)
    dialog.bind("<Escape>", lambda event: dialog.destroy())
    dialog.grab_set()
    project_list.focus_set()
    root.wait_window(dialog)

    return selection["project"]


def load_blacklist():
    bl = []
    try:
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                bl.append(line)
    except FileNotFoundError:
        return []

    return bl


class Theme:
    def __init__(self):
        self.dark_mode = False
        self.light_colors = {
            "bg": "#ffffff",
            "fg": "#000000",
            "button_bg": "#f0f0f0",
            "button_fg": "#000000",
            "label_bg": "#ffffff",
            "label_fg": "#000000",
            "text_bg": "#ffffff",
            "text_fg": "#000000",
            "image_bg": "#ffffff"
        }
        self.dark_colors = {
            "bg": "#2b2b2b",
            "fg": "#ffffff",
            "button_bg": "#404040",
            "button_fg": "#ffffff",
            "label_bg": "#2b2b2b",
            "label_fg": "#ffffff",
            "text_bg": "#1e1e1e",
            "text_fg": "#ffffff",
            "image_bg": "#000000"
        }

    def get_colors(self):
        return self.dark_colors if self.dark_mode else self.light_colors

    def toggle(self):
        self.dark_mode = not self.dark_mode
        return self.get_colors()


class App:

    def __init__(self, root):

        self.root = root
        self.theme = Theme()

        try:
            self.cfg = load_config()
        except Exception as e:
            messagebox.showerror("Error", str(e))
            root.destroy()
            return

        # Load the blacklist from Blacklist.txt
        try:
            self.blacklist = load_blacklist()
        except Exception:
            self.blacklist = []

        if not self.cfg.username or not self.cfg.api_key:
            messagebox.showerror(
                "Error",
                "Please provide username and api_key in config/config.txt"
            )
            root.destroy()
            return

        self.posts = []
        self.index = 0
        self.skip_set_id = None
        self.pending_actions = 0
        self.image_request_id = 0
        self.image_future = None
        self.animation_after_id = None
        self.animation_frames = []
        self.animation_index = 0
        self.video_path = None
        self.tag_edits_remaining = None
        self.tag_edits_since_quota_refresh = 0
        self.tag_edits_quota_refresh_pending = False
        self.closing = False
        self.ui_callbacks = queue.SimpleQueue()
        self.request_sessions = threading.local()
        self.api_executor = ThreadPoolExecutor(max_workers=1)
        self.image_executor = ThreadPoolExecutor(max_workers=2)
        self.vars = {}
        self.widgets = []
        self.root.bind_all("<KeyPress>", self.toggle_tag_shortcut)
        self.root.bind_all("<Return>", self.handle_action_shortcut)
        self.root.bind_all("<KP_Enter>", self.handle_action_shortcut)
        self.root.bind_all("<Left>", self.handle_action_shortcut)
        self.root.bind_all("<Right>", self.handle_action_shortcut)
        self.root.bind_all("<Button-1>", self.release_page_entry_focus, add="+")

        root.title("e621 Tag Editor")

        self.top_frame = tk.Frame(root)
        self.top_frame.pack(side="top", fill="x", padx=10, pady=5)

        self.theme_btn = tk.Button(
            self.top_frame,
            text="🌙 Dark Mode",
            command=self.toggle_theme,
            width=15
        )
        self.theme_btn.pack(side="left")
        self.widgets.append(self.theme_btn)

        # Pagination controls
        self.page = 1
        self.page_frame = tk.Frame(self.top_frame)
        self.page_frame.pack(side="left", padx=10)

        self.prev_page_btn = tk.Button(
            self.page_frame,
            text="Prev Page",
            width=10,
            command=lambda: self.change_page(-1)
        )
        self.prev_page_btn.pack(side="left", padx=(0, 5))

        self.page_label = tk.Label(self.page_frame, text=f"Page: {self.page}", width=12)
        self.page_label.pack(side="left")
        # Entry + Go button to jump directly to a page
        self.page_entry = tk.Entry(self.page_frame, width=6)
        self.page_entry.insert(0, str(self.page))
        self.page_entry.pack(side="left", padx=(5, 0))
        self.page_entry.bind("<Return>", lambda event: self.go_to_page())

        self.go_page_btn = tk.Button(
            self.page_frame,
            text="Go",
            width=6,
            command=self.go_to_page
        )
        self.go_page_btn.pack(side="left", padx=(5, 0))

        self.next_page_btn = tk.Button(
            self.page_frame,
            text="Next Page",
            width=10,
            command=lambda: self.change_page(1)
        )
        self.next_page_btn.pack(side="left", padx=(5, 0))

        self.change_project_btn = tk.Button(
            self.page_frame,
            text="Change project",
            command=self.change_tag_project
        )
        self.change_project_btn.pack(side="left", padx=(5, 0))

        self.reload_media_btn = tk.Button(
            self.page_frame,
            text="↻",
            width=3,
            command=self.reload_media
        )
        self.reload_media_btn.pack(side="left", padx=(5, 0))

        self.widgets.extend([
            self.page_frame,
            self.prev_page_btn,
            self.page_label,
            self.page_entry,
            self.go_page_btn,
            self.next_page_btn,
            self.change_project_btn,
            self.reload_media_btn
        ])

        self.tag_edits_label = tk.Label(
            root,
            text="Remaining tag edits this hour: loading..."
        )
        self.tag_edits_label.pack(anchor="w", padx=10)
        self.widgets.append(self.tag_edits_label)

        self.image_label = tk.Label(root)
        self.image_label.pack(padx=10, pady=10)
        self.image_label.bind("<Button-1>", self.open_current_media)
        self.widgets.append(self.image_label)

        self.current_image = None

        self.post_label = tk.Label(root, text="", wraplength=1000, justify="left")
        self.post_label.pack()
        self.widgets.append(self.post_label)

        self.status_label = tk.Label(root, text="", fg="green")
        self.status_label.pack(pady=(0, 10))
        self.widgets.append(self.status_label)

        self.checkbox_frame = tk.Frame(root)
        self.checkbox_frame.pack(pady=10, padx=10)
        self.widgets.append(self.checkbox_frame)
        self.create_tag_checkboxes()

        self.button_frame = tk.Frame(root)
        self.button_frame.pack(pady=10)
        self.widgets.append(self.button_frame)

        self.prev_btn = tk.Button(
            self.button_frame,
            text="Previous",
            width=15,
            command=self.previous
        )
        self.prev_btn.pack(side="left", padx=5)
        self.widgets.append(self.prev_btn)

        self.submit_btn = tk.Button(
            self.button_frame,
            text="Submit",
            width=15,
            command=self.submit
        )
        self.submit_btn.pack(side="left", padx=5)
        self.widgets.append(self.submit_btn)

        self.skip_btn = tk.Button(
            self.button_frame,
            text="Skip",
            width=15,
            command=self.skip
        )
        self.skip_btn.pack(side="left", padx=5)
        self.widgets.append(self.skip_btn)

        self.preview_text = tk.Text(root, width=100, height=12)
        self.preview_text.pack(padx=10, pady=10)
        self.widgets.append(self.preview_text)

        self.apply_theme()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(25, self.process_ui_callbacks)
        self.load_tag_edits_remaining()
        self.load_posts()

    def toggle_theme(self):
        colors = self.theme.toggle()
        self.apply_theme()

    def create_tag_checkboxes(self):
        for child in self.checkbox_frame.winfo_children():
            child.destroy()

        self.widgets = [
            widget for widget in self.widgets
            if not isinstance(widget, tk.Checkbutton)
        ]
        self.vars = {}
        for tag in self.cfg.add_tags:
            var = tk.BooleanVar()
            self.vars[tag] = var
            cb = tk.Checkbutton(
                self.checkbox_frame,
                text=tag,
                variable=var,
                anchor="center",
                justify="center",
                selectcolor="#4a4a4a"
            )
            cb.pack(pady=2, fill="x")
            self.widgets.append(cb)

    def change_tag_project(self):
        if self.pending_actions:
            self.status_label.config(
                text="Wait for the API actions to finish before changing projects.",
                fg="orange"
            )
            return

        try:
            projects = load_tag_projects()
            if not projects:
                raise RuntimeError(
                    f"No tag project found in {TAG_PROJECT_FILE}"
                )

            selected_project = choose_tag_project(self.root, projects)
            if selected_project is None:
                return

            selected_project = add_default_search_tags(
                selected_project,
                load_default_search_tags()
            )
            apply_tag_project(selected_project)
            self.cfg = load_config()
            self.create_tag_checkboxes()
            self.apply_theme()
            self.page = 1
            self.page_label.config(text=f"Page: {self.page}")
            self.page_entry.delete(0, tk.END)
            self.page_entry.insert(0, str(self.page))
            self.index = 0
            self.status_label.config(
                text=f"Project \"{selected_project['name']}\" loaded.",
                fg="green"
            )
            self.root.state("zoomed")
            self.load_posts()
        except Exception as e:
            messagebox.showerror(
                "Project change error",
                str(e),
                parent=self.root
            )

    def toggle_tag_shortcut(self, event):
        if event.widget.winfo_toplevel() is not self.root:
            return
        if isinstance(event.widget, (tk.Entry, tk.Text)):
            return

        key = event.char
        if key.lower() == "r":
            self.reload_media()
            return "break"

        if len(key) != 1 or key not in "0123456789":
            return

        index = 9 if key == "0" else int(key) - 1
        if index < 0 or index >= len(self.cfg.add_tags):
            return

        tag = self.cfg.add_tags[index]
        self.vars[tag].set(not self.vars[tag].get())
        return "break"

    def handle_action_shortcut(self, event):
        if event.widget.winfo_toplevel() is not self.root:
            return
        if isinstance(event.widget, (tk.Entry, tk.Text)):
            return

        if event.keysym in ("Return", "KP_Enter"):
            self.submit()
        elif event.keysym == "Right":
            self.skip()
        elif event.keysym == "Left":
            self.previous()
        else:
            return
        return "break"

    def release_page_entry_focus(self, event):
        if event.widget is self.page_entry:
            return
        if self.root.focus_get() is self.page_entry:
            self.root.focus_set()

    def open_fullscreen(self, event=None):
        if self.current_image is None:
            return

        fullscreen_window = tk.Toplevel(self.root)
        fullscreen_window.title("Image Viewer - Scroll to zoom, left-click and drag to move, right-click to close")
        
        canvas = tk.Canvas(fullscreen_window, bg="black", cursor="hand2")
        canvas.pack(fill="both", expand=True)

        self.zoom_level = 1.0
        self.fullscreen_image = self.current_image.copy()
        self.display_image = self.fullscreen_image
        self.photo_image = ImageTk.PhotoImage(self.display_image)
        self.offset_x = 0
        self.offset_y = 0
        self.drag_start = None
        
        image_id = canvas.create_image(self.offset_x, self.offset_y, image=self.photo_image, anchor="nw")

        def redraw_image():
            new_width = int(self.fullscreen_image.width * self.zoom_level)
            new_height = int(self.fullscreen_image.height * self.zoom_level)
            self.display_image = self.fullscreen_image.resize((new_width, new_height), Image.LANCZOS)
            self.photo_image = ImageTk.PhotoImage(self.display_image)
            canvas.itemconfig(image_id, image=self.photo_image)
            canvas.coords(image_id, self.offset_x, self.offset_y)

        def on_mousewheel(event):
            if event.delta > 0:
                self.zoom_level *= 1.2
            else:
                self.zoom_level /= 1.2
            
            self.zoom_level = max(0.5, min(self.zoom_level, 5.0))
            redraw_image()

        def on_left_click(event):
            self.drag_start = (event.x, event.y)

        def on_left_drag(event):
            if self.drag_start is None:
                return
            
            dx = event.x - self.drag_start[0]
            dy = event.y - self.drag_start[1]
            
            self.offset_x += dx
            self.offset_y += dy
            self.drag_start = (event.x, event.y)
            
            canvas.coords(image_id, self.offset_x, self.offset_y)

        def on_left_release(event):
            self.drag_start = None

        def on_right_click(event):
            fullscreen_window.destroy()

        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Button-1>", on_left_click)
        canvas.bind("<B1-Motion>", on_left_drag)
        canvas.bind("<ButtonRelease-1>", on_left_release)
        canvas.bind("<Button-3>", on_right_click)
        
        fullscreen_window.state("zoomed")

    def apply_theme(self):
        colors = self.theme.get_colors()
        self.root.config(bg=colors["bg"])

        self.theme_btn.config(
            bg=colors["button_bg"],
            fg=colors["button_fg"],
            text="☀️ Light Mode" if self.theme.dark_mode else "🌙 Dark Mode"
        )

        self.image_label.config(bg=colors["image_bg"])
        self.post_label.config(bg=colors["label_bg"], fg=colors["label_fg"])
        self.status_label.config(bg=colors["label_bg"], fg=colors["label_fg"])
        self.tag_edits_label.config(
            bg=colors["label_bg"],
            fg=colors["label_fg"]
        )
        self.top_frame.config(bg=colors["bg"])
        self.page_frame.config(bg=colors["bg"])
        self.checkbox_frame.config(bg=colors["bg"])
        self.button_frame.config(bg=colors["bg"])
        self.preview_text.config(
            bg=colors["text_bg"],
            fg=colors["text_fg"],
            insertbackground=colors["label_fg"]
        )

        select_color = "#5a5a5a" if self.theme.dark_mode else "#e0e0e0"
        for cb in [w for w in self.widgets if isinstance(w, tk.Checkbutton)]:
            cb.config(
                bg=colors["bg"],
                fg=colors["fg"],
                activebackground=colors["button_bg"],
                activeforeground=colors["fg"],
                selectcolor=select_color
            )

        self.submit_btn.config(
            bg=colors["button_bg"],
            fg=colors["button_fg"],
            activebackground=colors["label_bg"],
            activeforeground=colors["button_fg"]
        )
        self.skip_btn.config(
            bg=colors["button_bg"],
            fg=colors["button_fg"],
            activebackground=colors["label_bg"],
            activeforeground=colors["button_fg"]
        )
        self.prev_btn.config(
            bg=colors["button_bg"],
            fg=colors["button_fg"],
            activebackground=colors["label_bg"],
            activeforeground=colors["button_fg"]
        )
        self.reload_media_btn.config(
            bg=colors["button_bg"],
            fg=colors["button_fg"],
            activebackground=colors["label_bg"],
            activeforeground=colors["button_fg"]
        )
        # Page navigation buttons
        if hasattr(self, 'prev_page_btn'):
            self.prev_page_btn.config(
                bg=colors["button_bg"],
                fg=colors["button_fg"],
                activebackground=colors["label_bg"],
                activeforeground=colors["button_fg"]
            )
        if hasattr(self, 'next_page_btn'):
            self.next_page_btn.config(
                bg=colors["button_bg"],
                fg=colors["button_fg"],
                activebackground=colors["label_bg"],
                activeforeground=colors["button_fg"]
            )
        if hasattr(self, 'change_project_btn'):
            self.change_project_btn.config(
                bg=colors["button_bg"],
                fg=colors["button_fg"],
                activebackground=colors["label_bg"],
                activeforeground=colors["button_fg"]
            )
        if hasattr(self, 'page_label'):
            self.page_label.config(bg=colors["label_bg"], fg=colors["label_fg"])
        if hasattr(self, 'page_entry'):
            self.page_entry.config(
                bg=colors["text_bg"],
                fg=colors["text_fg"],
                insertbackground=colors["label_fg"],
                highlightbackground=colors["button_bg"]
            )
        if hasattr(self, 'go_page_btn'):
            self.go_page_btn.config(
                bg=colors["button_bg"],
                fg=colors["button_fg"],
                activebackground=colors["label_bg"],
                activeforeground=colors["button_fg"]
            )

    def request_headers(self):
        return {
            "User-Agent": self.cfg.user_agent,
            "Accept": "application/json"
        }

    def request_session(self):
        session = getattr(self.request_sessions, "session", None)
        if session is None:
            session = requests.Session()
            self.request_sessions.session = session
        return session

    def schedule_ui_callback(self, callback, *args):
        if self.closing:
            return
        self.ui_callbacks.put((callback, args))

    def process_ui_callbacks(self):
        while not self.closing:
            try:
                callback, args = self.ui_callbacks.get_nowait()
            except queue.Empty:
                break
            callback(*args)

        if not self.closing:
            self.root.after(25, self.process_ui_callbacks)

    def queue_api_action(
        self,
        action,
        post_id,
        operation,
        *args,
        counts_tag_edit=False
    ):
        self.pending_actions += 1
        self.status_label.config(
            text=f"{self.pending_actions} API action(s) pending...",
            fg="black"
        )
        future = self.api_executor.submit(operation, *args)
        future.add_done_callback(
            lambda completed: self.schedule_ui_callback(
                self.finish_api_action,
                completed,
                action,
                post_id,
                counts_tag_edit
            )
        )

    def finish_api_action(
        self,
        future,
        action,
        post_id,
        counts_tag_edit=False
    ):
        self.pending_actions -= 1
        try:
            future.result()
        except Exception as e:
            error = f"Error {action} for post {post_id}: {e}"
            self.status_label.config(text=error, fg="red")
            messagebox.showerror("API Error", error, parent=self.root)
            return

        if counts_tag_edit:
            self.tag_edits_since_quota_refresh += 1
            if self.tag_edits_remaining is not None:
                self.tag_edits_remaining = max(
                    0,
                    self.tag_edits_remaining - 1
                )
                self.update_tag_edits_label()
            if (
                self.tag_edits_since_quota_refresh
                >= TAG_EDIT_QUOTA_REFRESH_INTERVAL
                and not self.tag_edits_quota_refresh_pending
            ):
                self.load_tag_edits_remaining()

        if self.pending_actions:
            self.status_label.config(
                text=f"{self.pending_actions} API action(s) pending...",
                fg="black"
            )
        else:
            self.status_label.config(
                text=f"Action completed for post {post_id}.",
                fg="green"
            )

    def load_tag_edits_remaining(self):
        if self.tag_edits_quota_refresh_pending:
            return
        self.tag_edits_quota_refresh_pending = True
        future = self.api_executor.submit(self.fetch_tag_edits_remaining)
        future.add_done_callback(
            lambda completed: self.schedule_ui_callback(
                self.finish_tag_edits_load,
                completed
            )
        )

    def fetch_tag_edits_remaining(self):
        username = requests.utils.quote(self.cfg.username, safe="")
        response = self.request_session().get(
            f"{BASE_URL}/users/{username}/upload_limit.html",
            headers={
                "User-Agent": self.cfg.user_agent,
                "Accept": "text/html"
            },
            auth=(self.cfg.username, self.cfg.api_key),
            timeout=20
        )
        response.raise_for_status()
        return parse_remaining_tag_edits(response.text)

    def finish_tag_edits_load(self, future):
        try:
            remaining = future.result()
        except Exception as e:
            self.tag_edits_quota_refresh_pending = False
            self.tag_edits_label.config(
                text=f"Tag edit quota unavailable: {e}",
                fg="red"
            )
            return

        self.tag_edits_quota_refresh_pending = False
        self.tag_edits_since_quota_refresh = 0
        self.tag_edits_remaining = max(0, remaining)
        self.update_tag_edits_label()

    def update_tag_edits_label(self):
        self.tag_edits_label.config(
            text=(
                "Remaining hourly tag edits : "
                f"{self.tag_edits_remaining}"
            )
        )

    def close(self):
        self.closing = True
        self.invalidate_image_request()
        self.api_executor.shutdown(wait=False, cancel_futures=True)
        self.image_executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()

    def change_page(self, delta):
        new_page = self.page + delta
        if new_page < 1:
            self.status_label.config(text="You are already on the first page.", fg="orange")
            return
        self.page = new_page
        self.page_label.config(text=f"Page: {self.page}")
        self.index = 0
        self.status_label.config(text=f"Loading page {self.page}...", fg="black")
        self.load_posts()

    def go_to_page(self):
        val = self.page_entry.get().strip()
        try:
            p = int(val)
            if p < 1:
                raise ValueError()
        except ValueError:
            self.status_label.config(text="Invalid page number.", fg="red")
            return

        self.page = p
        self.page_label.config(text=f"Page: {self.page}")
        self.index = 0
        self.status_label.config(text=f"Loading page {self.page}...", fg="black")
        self.load_posts()
        self.root.focus_set()

    def load_posts(self):
        self.invalidate_image_request()
        self.image_label.config(image="")
        self.current_image = None
        params = {
            "limit": int(self.cfg.limit)
        }
        # Page number for pagination
        params["page"] = self.page
        # Build the tag search string including blacklist exclusions
        tags = self.cfg.search_tags or ""
        if getattr(self, 'blacklist', None):
            negs = " ".join(f"-{t}" for t in self.blacklist if t)
            if negs:
                tags = (tags + " " + negs).strip() if tags else negs

        if self.cfg.set_shortname:
            try:
                self.skip_set_id = self.get_skip_set_id()
                set_filter = f"-set:{self.skip_set_id}"
                tags = (tags + " " + set_filter).strip() if tags else set_filter
            except Exception as e:
                self.post_label.config(text=f"Loading error: {e}")
                self.status_label.config(text=f"Loading error: {e}", fg="red")
                return

        if tags:
            params["tags"] = tags

        try:
            r = self.request_session().get(
                f"{BASE_URL}/posts.json",
                params=params,
                headers=self.request_headers(),
                auth=(self.cfg.username, self.cfg.api_key),
                timeout=20
            )
            r.raise_for_status()
            self.posts = r.json().get("posts", [])

            if not self.posts:
                self.post_label.config(text="No results.")
                self.image_label.config(image="")
                self.status_label.config(text="No results for this page.", fg="orange")
                return

            # Reset index for the new page
            self.index = 0
            self.show_post()

        except Exception as e:
            self.post_label.config(text=f"Loading error: {e}")
            self.status_label.config(text=f"Loading error: {e}", fg="red")

    def get_skip_set_id(self):
        if self.skip_set_id is not None:
            return self.skip_set_id

        response = self.request_session().get(
            f"{BASE_URL}/post_sets.json",
            params={"search[shortname]": self.cfg.set_shortname},
            headers=self.request_headers(),
            auth=(self.cfg.username, self.cfg.api_key),
            timeout=20
        )
        response.raise_for_status()
        post_sets = response.json()
        matches = [
            post_set for post_set in post_sets
            if post_set.get("shortname") == self.cfg.set_shortname
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"Set not found or ambiguous for shortname "
                f"'{self.cfg.set_shortname}'."
            )

        self.skip_set_id = matches[0].get("id")
        if self.skip_set_id is None:
            raise RuntimeError(
                f"The API did not provide the set ID for "
                f"'{self.cfg.set_shortname}'."
            )
        return self.skip_set_id

    def add_post_to_skip_set(self, post_id):
        if post_id is None:
            raise RuntimeError("The post ID is missing.")

        set_id = self.get_skip_set_id()
        response = self.request_session().post(
            f"{BASE_URL}/post_sets/{set_id}/add_posts.json",
            headers=self.request_headers(),
            auth=(self.cfg.username, self.cfg.api_key),
            data={"post_ids[]": post_id},
            timeout=20
        )
        response.raise_for_status()

    def show_post(self):
        self.invalidate_image_request()
        if self.index >= len(self.posts):
            self.post_label.config(text="End of results.")
            self.image_label.config(image="")
            self.status_label.config(text="")
            self.current_image = None
            return

        for var in self.vars.values():
            var.set(False)

        post = self.posts[self.index]
        post_id = post.get("id")
        self.post_label.config(text=f"Post ID: {post_id}")

        existing_tags = []
        for category_tags in post.get("tags", {}).values():
            existing_tags.extend(category_tags)

        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert(
            tk.END,
            "CURRENT TAGS:\n"
            + " ".join(sorted(existing_tags))
            + "\n\n"
            + "TAGS AVAILABLE TO ADD:\n"
            + " ".join(self.cfg.add_tags)
        )

        self.load_post_media(post)

    def reload_media(self):
        if self.index >= len(self.posts):
            self.status_label.config(text="No post to reload.", fg="orange")
            return

        self.invalidate_image_request()
        self.load_post_media(self.posts[self.index])

    def load_post_media(self, post):
        post_file = post.get("file", {})
        image_url = post_file.get("url") or post.get("sample", {}).get("url")
        media_ext = post_file.get("ext") or os.path.splitext(
            urlparse(image_url or "").path
        )[1]
        media_ext = f".{media_ext.lstrip('.').lower()}" if media_ext else ""
        self.image_label.config(image="", text="")
        self.current_image = None
        if not image_url:
            self.status_label.config(text="No image found.", fg="red")
            return

        if not self.pending_actions:
            self.status_label.config(text="Loading image...", fg="black")
        image_request_id = self.image_request_id
        self.image_future = self.image_executor.submit(
            self.download_media,
            image_url,
            media_ext
        )
        self.image_future.add_done_callback(
            lambda completed: self.media_load_completed(
                completed, image_request_id
            )
        )

    def invalidate_image_request(self):
        self.image_request_id += 1
        if self.image_future is not None:
            self.image_future.cancel()
            self.image_future = None
        if self.animation_after_id is not None:
            self.root.after_cancel(self.animation_after_id)
            self.animation_after_id = None
        self.animation_frames = []
        self.animation_index = 0
        video_path = self.video_path
        self.video_path = None
        if video_path:
            self.remove_video_file(video_path)

    @staticmethod
    def remove_video_file(video_path):
        try:
            os.remove(video_path)
        except FileNotFoundError:
            pass
        except OSError as error:
            logging.warning("Could not remove video file %s: %s", video_path, error)

    def download_media(self, image_url, media_ext):
        if media_ext in VIDEO_EXTENSIONS:
            os.makedirs(VIDEO_DIRECTORY, exist_ok=True)
            temp_file = tempfile.NamedTemporaryFile(
                prefix="e621-tag-editor-",
                suffix=media_ext,
                dir=VIDEO_DIRECTORY,
                delete=False
            )
            video_path = temp_file.name
            try:
                with temp_file:
                    with self.request_session().get(
                        image_url,
                        headers=self.request_headers(),
                        timeout=60,
                        stream=True
                    ) as response:
                        response.raise_for_status()
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                temp_file.write(chunk)
                return "video", video_path
            except Exception:
                try:
                    os.remove(video_path)
                except FileNotFoundError:
                    pass
                raise

        response = self.request_session().get(
            image_url,
            headers=self.request_headers(),
            timeout=20
        )
        response.raise_for_status()
        with Image.open(io.BytesIO(response.content)) as image:
            frames = []
            frame_count = getattr(image, "n_frames", 1)
            for frame_index in range(frame_count):
                image.seek(frame_index)
                frames.append((
                    image.copy(),
                    max(20, int(image.info.get("duration", 100)))
                ))
            return "image", frames

    def media_load_completed(self, future, image_request_id):
        if self.closing:
            self.discard_downloaded_video(future)
            return
        self.schedule_ui_callback(
            self.finish_media_load, future, image_request_id
        )

    def discard_downloaded_video(self, future):
        try:
            media_type, media = future.result()
        except Exception:
            return
        if media_type == "video":
            self.remove_video_file(media)

    def finish_media_load(self, future, image_request_id):
        if image_request_id != self.image_request_id:
            self.discard_downloaded_video(future)
            return
        self.image_future = None
        try:
            media_type, media = future.result()
        except Exception as e:
            self.image_label.config(image="", text="")
            self.status_label.config(text=f"Media error: {e}", fg="red")
            return

        if media_type == "video":
            self.video_path = media
            self.image_label.config(
                text="Video ready\nClick here to open it",
                cursor="hand2"
            )
            if not self.pending_actions:
                self.status_label.config(
                    text="Video ready. Click the preview to open it.",
                    fg="green"
                )
            return

        self.animation_frames = []
        for frame, duration in media:
            display_frame = frame.copy()
            thumbnail = frame.copy()
            thumbnail.thumbnail((900, 500), Image.LANCZOS)
            self.animation_frames.append((display_frame, thumbnail, duration))
        self.display_animation_frame(0)
        if len(self.animation_frames) > 1:
            self.animation_after_id = self.root.after(
                self.animation_frames[0][2],
                self.animate_gif
            )
        if not self.pending_actions:
            self.status_label.config(
                text="Media loaded. Click to open in full screen.",
                fg="green"
            )

    def display_animation_frame(self, frame_index):
        full_frame, thumbnail, _ = self.animation_frames[frame_index]
        self.animation_index = frame_index
        self.current_image = full_frame.copy()
        self.tk_image = ImageTk.PhotoImage(thumbnail)
        self.image_label.config(image=self.tk_image, text="", cursor="hand2")

    def animate_gif(self):
        if len(self.animation_frames) < 2:
            self.animation_after_id = None
            return
        next_index = (self.animation_index + 1) % len(self.animation_frames)
        self.display_animation_frame(next_index)
        self.animation_after_id = self.root.after(
            self.animation_frames[next_index][2],
            self.animate_gif
        )

    def open_current_media(self, event=None):
        if self.video_path:
            if os.name != "nt":
                self.status_label.config(
                    text="Opening videos is available on Windows.",
                    fg="red"
                )
                return
            try:
                os.startfile(self.video_path)
            except OSError as error:
                self.status_label.config(
                    text=f"Unable to open the video: {error}",
                    fg="red"
                )
            return
        self.open_fullscreen()

    def update_post_tags(self, post_id, tags):
        data = {
            "post[tag_string]": " ".join(tags)
        }
        url = f"{BASE_URL}/posts/{post_id}.json"
        methods = ["post", "patch", "put"]

        last_error = None
        for method in methods:
            r = self.request_session().request(
                method,
                url,
                headers=self.request_headers(),
                auth=(self.cfg.username, self.cfg.api_key),
                data=data,
                timeout=20
            )
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                last_error = r
                continue
            raise RuntimeError(
                f"Update error ({r.status_code}): {r.text[:200]}"
            )

        raise RuntimeError(
            f"Update error (404): {last_error.text[:200] if last_error is not None else 'Not Found'}"
        )

    def submit(self):
        if self.index >= len(self.posts):
            return

        post = self.posts[self.index]
        existing_tags = []
        for category_tags in post.get("tags", {}).values():
            existing_tags.extend(category_tags)

        selected_tags = [tag for tag, var in self.vars.items() if var.get()]
        if not selected_tags:
            self.status_label.config(text="No tag selected. Use Skip to continue.", fg="orange")
            return

        merged_tags = sorted(set(existing_tags) | set(selected_tags))
        post_id = post.get("id")
        if post_id is None:
            self.status_label.config(
                text="Update error: post ID missing.",
                fg="red"
            )
            return

        self.queue_api_action(
            "mise à jour",
            post_id,
            self.update_post_tags,
            post_id,
            merged_tags,
            counts_tag_edit=True
        )
        self.index += 1
        self.show_post()

    def skip(self):
        if self.index >= len(self.posts):
            return

        post_id = self.posts[self.index].get("id")
        if self.cfg.set_shortname:
            if post_id is None:
                self.status_label.config(
                    text="Set add error: post ID missing.",
                    fg="red"
                )
                return
            self.queue_api_action(
                "ajout au set",
                post_id,
                self.add_post_to_skip_set,
                post_id
            )

        self.index += 1
        if not self.pending_actions:
            self.status_label.config(text="Next post...", fg="black")
        self.show_post()

    def previous(self):
        if self.index > 0:
            self.index -= 1
            self.status_label.config(text="Previous post...", fg="black")
            self.show_post()
        else:
            self.status_label.config(text="You are at the first post.", fg="orange")


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    selected_project = None
    try:
        projects = load_tag_projects()
        if not projects:
            raise RuntimeError(f"No tag project found in {TAG_PROJECT_FILE}")
        selected_project = choose_tag_project(root, projects)
        if selected_project is not None:
            default_tags = load_default_search_tags()
            selected_project = add_default_search_tags(selected_project, default_tags)
            apply_tag_project(selected_project)
    except Exception as e:
        root.deiconify()
        messagebox.showerror("Error", str(e), parent=root)
        root.destroy()
    else:
        if selected_project is None:
            root.destroy()
        else:
            root.deiconify()
            App(root)
            root.state("zoomed")
            root.mainloop()