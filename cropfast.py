#!/usr/bin/env python3
import sys
import os
import configparser
from pathlib import Path
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')
APP_VERSION = "1.0.0"

# --- Configuration ---
CONFIG_DIR = Path.home() / ".config/cropfast"
CONFIG_FILE = CONFIG_DIR / "config.cfg"

def _xdg_user_dir(special_dir, fallback_name):
    """Resolve a standard user folder (Downloads, Pictures, ...) the
    freedesktop way, via xdg-user-dirs. This respects the actual,
    possibly localized, folder name the user has configured
    (e.g. 'Stiahnuté' instead of 'Downloads') instead of assuming an
    English name. Falls back to home/<fallback_name> if XDG has
    nothing configured (e.g. minimal systems without xdg-user-dirs)."""
    try:
        path = GLib.get_user_special_dir(special_dir)
        if path:
            return Path(path)
    except Exception:
        pass
    return Path.home() / fallback_name

DEFAULT_OUTPUT_DIR = _xdg_user_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD, "Downloads")

DEFAULT_CONFIG = {
    'Paths': {
        'output_folder': str(DEFAULT_OUTPUT_DIR),
        # Intentionally no default here — until the user sets one in
        # Settings (or passes a path on the command line), the app shows
        # the "open an image or folder" placeholder instead of guessing.
        'default_input_folder': ''
    },
    'Crop': {
        'ratios': '3:2, 4:3, 16:9, 1:1, 5:4',
        'current_ratio': '3:2',
        'startup_mode': 'auto'   # portrait / landscape / auto / freehand
    },
    'Sorting': {
        'sort_by': 'name',
        'sort_order': 'ascending'
    }
}

def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = configparser.ConfigParser()
    if not CONFIG_FILE.exists():
        for section, options in DEFAULT_CONFIG.items():
            config[section] = options
        save_config(config)
    else:
        config.read(CONFIG_FILE)
        changed = False
        for section, options in DEFAULT_CONFIG.items():
            if section not in config:
                config[section] = {}
                changed = True
            for k, v in options.items():
                if k not in config[section]:
                    config[section][k] = v
                    changed = True
        if changed:
            save_config(config)
    return config

def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        config.write(f)

def parse_ratio(ratio_str):
    try:
        ratio_str = ratio_str.strip().replace(',', '.').replace('/', ':')
        if ':' not in ratio_str:
            return None
        w, h = ratio_str.split(':', 1)
        w, h = float(w), float(h)
        if w <= 0 or h <= 0:
            return None
        return w, h
    except Exception:
        return None


class SettingsDialog(Gtk.Window):
    """Simple settings window: output/input folders, ratio list,
    startup mode and file sorting."""

    def __init__(self, parent):
        super().__init__(transient_for=parent, modal=True, title="Settings")
        self.parent_app = parent
        self.set_default_size(480, 0)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_top(16)
        outer.set_margin_bottom(16)
        outer.set_margin_start(16)
        outer.set_margin_end(16)
        self.set_child(outer)

        grid = Gtk.Grid(row_spacing=8, column_spacing=8)
        outer.append(grid)
        row = 0

        # Output folder
        grid.attach(Gtk.Label(label="Output folder:", halign=Gtk.Align.START), 0, row, 1, 1)
        self.entry_output = Gtk.Entry(hexpand=True)
        self.entry_output.set_text(parent.config.get('Paths', 'output_folder', fallback=''))
        grid.attach(self.entry_output, 1, row, 1, 1)
        btn_out = Gtk.Button(label="Browse…")
        btn_out.connect("clicked", lambda b: self._browse_folder(self.entry_output))
        grid.attach(btn_out, 2, row, 1, 1)
        row += 1

        # Default input folder
        grid.attach(Gtk.Label(label="Default input folder:", halign=Gtk.Align.START), 0, row, 1, 1)
        self.entry_input = Gtk.Entry(hexpand=True)
        self.entry_input.set_placeholder_text("Not set — the app will ask each time")
        self.entry_input.set_text(parent.config.get('Paths', 'default_input_folder', fallback=''))
        grid.attach(self.entry_input, 1, row, 1, 1)
        btn_in = Gtk.Button(label="Browse…")
        btn_in.connect("clicked", lambda b: self._browse_folder(self.entry_input))
        grid.attach(btn_in, 2, row, 1, 1)
        row += 1

        # Crop ratios
        grid.attach(Gtk.Label(label="Ratios (comma-separated):", halign=Gtk.Align.START), 0, row, 1, 1)
        self.entry_ratios = Gtk.Entry(hexpand=True)
        self.entry_ratios.set_text(parent.config.get('Crop', 'ratios', fallback=''))
        grid.attach(self.entry_ratios, 1, row, 2, 1)
        row += 1

        # Startup mode
        grid.attach(Gtk.Label(label="Startup mode:", halign=Gtk.Align.START), 0, row, 1, 1)
        modes = ['portrait', 'landscape', 'auto', 'freehand']
        mode_labels = ['Portrait', 'Landscape', 'Adaptive', 'Freehand']
        self.combo_startup = Gtk.DropDown(model=Gtk.StringList.new(mode_labels))
        current_mode = parent.config.get('Crop', 'startup_mode', fallback='auto').strip().lower()
        self.combo_startup.set_selected(modes.index(current_mode) if current_mode in modes else modes.index('auto'))
        grid.attach(self.combo_startup, 1, row, 2, 1)
        row += 1

        # Sort by
        grid.attach(Gtk.Label(label="Sort images by:", halign=Gtk.Align.START), 0, row, 1, 1)
        sort_opts = ['date', 'name']
        self.combo_sort_by = Gtk.DropDown(model=Gtk.StringList.new(sort_opts))
        cur_sort_by = parent.config.get('Sorting', 'sort_by', fallback='name').strip().lower()
        self.combo_sort_by.set_selected(sort_opts.index(cur_sort_by) if cur_sort_by in sort_opts else sort_opts.index('name'))
        grid.attach(self.combo_sort_by, 1, row, 2, 1)
        row += 1

        # Sort order
        grid.attach(Gtk.Label(label="Sort order:", halign=Gtk.Align.START), 0, row, 1, 1)
        order_opts = ['ascending', 'descending']
        self.combo_sort_order = Gtk.DropDown(model=Gtk.StringList.new(order_opts))
        cur_order = parent.config.get('Sorting', 'sort_order', fallback='ascending').strip().lower()
        self.combo_sort_order.set_selected(order_opts.index(cur_order) if cur_order in order_opts else order_opts.index('ascending'))
        grid.attach(self.combo_sort_order, 1, row, 2, 1)
        row += 1

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        outer.append(btn_box)

        btn_cancel = Gtk.Button(label="Cancel")
        btn_cancel.connect("clicked", lambda b: self.close())
        btn_box.append(btn_cancel)

        btn_save = Gtk.Button(label="Save")
        btn_save.add_css_class("suggested-action")
        btn_save.connect("clicked", self._on_save)
        btn_box.append(btn_save)

    def _browse_folder(self, entry):
        chooser = Gtk.FileChooserNative.new(
            "Select Folder", self, Gtk.FileChooserAction.SELECT_FOLDER, "Select", "Cancel")
        chooser.connect("response", self._on_folder_chosen, entry)
        self._active_chooser = chooser
        chooser.show()

    def _on_folder_chosen(self, chooser, response, entry):
        if response == Gtk.ResponseType.ACCEPT:
            gfile = chooser.get_file()
            if gfile and gfile.get_path():
                entry.set_text(gfile.get_path())
        self._active_chooser = None

    def _on_save(self, button):
        cfg = self.parent_app.config

        ratios_text = self.entry_ratios.get_text().strip()
        new_ratios = None
        if ratios_text:
            raw_items = [r.strip() for r in ratios_text.split(',') if r.strip()]
            valid_items, invalid_items, seen = [], [], set()
            for item in raw_items:
                parsed = parse_ratio(item)
                if parsed is None:
                    invalid_items.append(item)
                    continue
                w, h = parsed
                clean = f"{int(w) if w.is_integer() else w}:{int(h) if h.is_integer() else h}"
                if clean not in seen:
                    seen.add(clean)
                    valid_items.append(clean)

            if not valid_items:
                self.parent_app._show_message_dialog(
                    "Invalid Ratios",
                    "None of the entered ratios are valid (expected format like "
                    "\u201c3:2\u201d). Fix the list before saving.",
                    is_error=True
                )
                return  # keep the dialog open so the user can fix it

            new_ratios = ', '.join(valid_items)
            self.entry_ratios.set_text(new_ratios)
            if invalid_items:
                self.parent_app._show_message_dialog(
                    "Some Ratios Ignored",
                    "These entries weren't valid and were skipped:\n" + ", ".join(invalid_items)
                )

        cfg['Paths']['output_folder'] = self.entry_output.get_text().strip() or cfg['Paths']['output_folder']
        # Unlike output_folder, an empty value here is valid and meaningful
        # (it means "not set yet" — the app keeps asking), so it's saved
        # as-is rather than falling back to the previous value.
        cfg['Paths']['default_input_folder'] = self.entry_input.get_text().strip()
        if new_ratios:
            cfg['Crop']['ratios'] = new_ratios

        modes = ['portrait', 'landscape', 'auto', 'freehand']
        cfg['Crop']['startup_mode'] = modes[self.combo_startup.get_selected()]

        sort_opts = ['date', 'name']
        cfg['Sorting']['sort_by'] = sort_opts[self.combo_sort_by.get_selected()]

        order_opts = ['ascending', 'descending']
        cfg['Sorting']['sort_order'] = order_opts[self.combo_sort_order.get_selected()]

        save_config(cfg)
        self.parent_app.refresh_ratio_list()
        self.close()


class CropApp(Gtk.ApplicationWindow):
    def __init__(self, app, initial_path=None):
        super().__init__(application=app, title="CropFast")
        self.config = load_config()

        self.files = []
        self.current_index = -1
        self.image_path = None
        self.orig_pixbuf = None
        self._active_chooser = None

        self._resolve_initial_path(initial_path)
        self.set_default_size(1200, 800)

        # Active mode: 'portrait' / 'landscape' / 'auto' / 'freehand'.
        # Starts as None (no real mode yet) so the very first call to
        # _apply_startup_mode() always applies its orientation, even if
        # the configured startup mode is the same as our first real mode.
        self.mode = None
        self.has_selection = True      # whether a selection is currently shown
        self.MIN_CROP = 20
        self.HANDLE_MARGIN = 10
        self.drag_start = None
        self.drag_mode = None

        # Cache of the size entry texts (to avoid needless rewrites)
        self._cache_w = None
        self._cache_h = None
        self._updating_entries = False

        self.current_ratio_str = self.config.get('Crop', 'current_ratio', fallback='3:2')
        self.startup_mode = self.config.get('Crop', 'startup_mode', fallback='auto').strip().lower()

        # Build the GUI
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(main_box)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_start(8)
        toolbar.set_margin_end(8)
        toolbar.set_margin_top(6)
        toolbar.set_margin_bottom(6)
        main_box.append(toolbar)

        # Open button (first in the toolbar) – pick an image or a folder.
        # A tiny popover (not a full dialog window) lets you choose which,
        # since GTK has no single dialog mode that reliably selects both.
        self.btn_open = Gtk.MenuButton(label="Open")
        self.btn_open.set_tooltip_text("Open an image or a folder of images (Ctrl+O)")
        toolbar.append(self.btn_open)

        self.open_popover = Gtk.Popover()
        open_popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        open_popover_box.set_margin_top(6)
        open_popover_box.set_margin_bottom(6)
        open_popover_box.set_margin_start(6)
        open_popover_box.set_margin_end(6)
        self.open_popover.set_child(open_popover_box)
        self.btn_open.set_popover(self.open_popover)

        btn_open_image = Gtk.Button(label="Image…")
        btn_open_image.set_has_frame(False)
        btn_open_image.connect("clicked", lambda b: (self.open_popover.popdown(), self._open_file_chooser('file')))
        open_popover_box.append(btn_open_image)

        btn_open_folder = Gtk.Button(label="Folder…")
        btn_open_folder.set_has_frame(False)
        btn_open_folder.connect("clicked", lambda b: (self.open_popover.popdown(), self._open_file_chooser('folder')))
        open_popover_box.append(btn_open_folder)

        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # Navigation buttons
        btn_prev = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        btn_prev.set_tooltip_text("Previous image (Left arrow)")
        btn_prev.connect("clicked", lambda b: self.navigate_image(-1))
        toolbar.append(btn_prev)

        btn_next = Gtk.Button.new_from_icon_name("go-next-symbolic")
        btn_next.set_tooltip_text("Next image (Right arrow)")
        btn_next.connect("clicked", lambda b: self.navigate_image(1))
        toolbar.append(btn_next)

        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # Ratio dropdown
        ratios_list = [r.strip() for r in self.config.get('Crop', 'ratios', fallback='3:2, 4:3, 16:9').split(',') if r.strip()]
        self.ratio_store = Gtk.StringList.new(ratios_list)
        self.combo_ratio = Gtk.DropDown(model=self.ratio_store)

        try:
            sel_idx = ratios_list.index(self.current_ratio_str)
            self.combo_ratio.set_selected(sel_idx)
        except ValueError:
            self.combo_ratio.set_selected(0)

        self.combo_ratio.connect("notify::selected", self.on_ratio_combo_changed)
        toolbar.append(self.combo_ratio)

        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # Mode buttons (mutually exclusive, active one is highlighted)
        self.btn_portrait = Gtk.Button(label="Portrait")
        self.btn_portrait.set_tooltip_text("Portrait mode – selection in portrait orientation")
        self.btn_portrait.connect("clicked", lambda b: self.set_mode('portrait'))
        toolbar.append(self.btn_portrait)

        self.btn_landscape = Gtk.Button(label="Landscape")
        self.btn_landscape.set_tooltip_text("Landscape mode – selection in landscape orientation")
        self.btn_landscape.connect("clicked", lambda b: self.set_mode('landscape'))
        toolbar.append(self.btn_landscape)

        self.btn_auto = Gtk.Button(label="Adaptive")
        self.btn_auto.set_tooltip_text("Selection automatically adapts to each image's orientation (also while browsing)")
        self.btn_auto.connect("clicked", lambda b: self.set_mode('auto'))
        toolbar.append(self.btn_auto)

        self.btn_freehand = Gtk.Button(label="Freehand")
        self.btn_freehand.set_tooltip_text("Freehand – selection is drawn with the mouse (turns off Portrait / Landscape / Auto)")
        self.btn_freehand.connect("clicked", lambda b: self.set_mode('freehand'))
        toolbar.append(self.btn_freehand)

        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # Selection size entry fields (px)
        # Enter in the field applies the value; clicking away also confirms it.
        size_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        self.entry_w = Gtk.Entry()
        self.entry_w.set_width_chars(5)
        self.entry_w.set_max_width_chars(7)   # <-- FIX: width cap, field won't grow even with long text
        self.entry_w.set_max_length(7)
        self.entry_w.set_alignment(1.0)
        self.entry_w.set_tooltip_text(
            "Selection width in px. Enter applies it (height is computed if the ratio is locked).")
        self.entry_w.connect("activate", lambda e: self._apply_entry_size('w'))
        self._add_entry_focus_watch(self.entry_w, 'w')
        size_box.append(self.entry_w)

        lbl_x = Gtk.Label(label="×")
        size_box.append(lbl_x)

        self.entry_h = Gtk.Entry()
        self.entry_h.set_width_chars(5)
        self.entry_h.set_max_width_chars(7)
        self.entry_h.set_max_length(7)
        self.entry_h.set_alignment(1.0)
        self.entry_h.set_tooltip_text(
            "Selection height in px. Enter applies it (width is computed if the ratio is locked).")
        self.entry_h.connect("activate", lambda e: self._apply_entry_size('h'))
        self._add_entry_focus_watch(self.entry_h, 'h')
        size_box.append(self.entry_h)

        toolbar.append(size_box)

        toolbar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        btn_crop = Gtk.Button(label="Crop")
        btn_crop.set_tooltip_text("Enter – crop and stay | Right-click – crop and go to next")
        btn_crop.add_css_class("suggested-action")
        btn_crop.connect("clicked", lambda b: self.do_crop())
        toolbar.append(btn_crop)

        # Spacer before the settings/close buttons
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)

        # About / help button
        btn_about = Gtk.Button.new_from_icon_name("help-about-symbolic")
        btn_about.set_tooltip_text("About & keyboard shortcuts")
        btn_about.connect("clicked", lambda b: self._open_about())
        toolbar.append(btn_about)

        # Settings button
        btn_settings = Gtk.Button.new_from_icon_name("emblem-system-symbolic")
        btn_settings.set_tooltip_text("Settings")
        btn_settings.connect("clicked", lambda b: self._open_settings())
        toolbar.append(btn_settings)

        # Close button
        btn_close = Gtk.Button(label="✕")
        btn_close.set_tooltip_text("Close the application (Esc)")
        btn_close.connect("clicked", lambda b: self.close())
        toolbar.append(btn_close)

        # Drawing area
        self.area = Gtk.DrawingArea()
        self.area.set_draw_func(self.on_draw)
        self.area.set_hexpand(True)
        self.area.set_vexpand(True)
        main_box.append(self.area)

        # 1. Left mouse button (move / drag corners / draw selection)
        click = Gtk.GestureClick.new()
        click.set_button(1)
        click.connect("pressed", self.on_press)
        click.connect("released", self.on_release)
        self.area.add_controller(click)

        # 2. Right mouse button (crop + move to next image)
        right_click = Gtk.GestureClick.new()
        right_click.set_button(3)
        right_click.connect("pressed", lambda *a: self.do_crop(advance=True))
        self.area.add_controller(right_click)

        # 3. Mouse wheel (browse between images)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self.on_scroll)
        self.area.add_controller(scroll)

        # 4. Mouse motion
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self.on_motion)
        self.area.add_controller(motion)

        # 5. Keyboard shortcuts (Enter, Esc, F, Left/Right arrows, Ctrl+O)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self.on_key)
        self.add_controller(key)

        self.area.connect("resize", lambda *a: self.area.queue_draw())

        self.load_current_image()
        self._apply_startup_mode()

    @property
    def freehand_mode(self):
        """True if freehand mode is active."""
        return self.mode == 'freehand'

    # --- Source picker (Open button) ---
    def _open_file_chooser(self, mode):
        """Opens the native chooser for either a single image file or a
        whole folder. Two separate dialog actions are used because GTK
        has no single mode that reliably lets you pick a folder itself
        (rather than just navigate into it) while also allowing files."""
        if mode == 'file':
            chooser = Gtk.FileChooserNative.new(
                "Select Image", self, Gtk.FileChooserAction.OPEN, "Open", "Cancel")
            filt = Gtk.FileFilter()
            filt.set_name("Images")
            for ext in IMAGE_EXTS:
                filt.add_pattern(f"*{ext}")
                filt.add_pattern(f"*{ext.upper()}")
            chooser.add_filter(filt)
        else:
            chooser = Gtk.FileChooserNative.new(
                "Select Folder", self, Gtk.FileChooserAction.SELECT_FOLDER, "Open", "Cancel")

        chooser.connect("response", self._on_source_chosen)
        self._active_chooser = chooser  # keep a reference alive while shown
        chooser.show()

    def _on_source_chosen(self, chooser, response):
        if response == Gtk.ResponseType.ACCEPT:
            gfile = chooser.get_file()
            if gfile and gfile.get_path():
                self._load_source(Path(gfile.get_path()))
        self._active_chooser = None

    def _load_source(self, path):
        self._resolve_initial_path(str(path))
        if self.files:
            # Only used for this session — opening something via the Open
            # button does NOT change the saved default_input_folder;
            # that's only set explicitly through Settings.
            self.load_current_image()
            self._apply_startup_mode()
        else:
            self._show_no_images_dialog()

    def _show_no_images_dialog(self):
        dialog = Gtk.Window(transient_for=self, modal=True, title="No Images Found")
        dialog.set_default_size(340, 0)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        dialog.set_child(box)

        label = Gtk.Label(label="No supported images were found there. Try another image or folder.")
        label.set_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        box.append(label)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.CENTER)
        box.append(btn_row)

        btn_retry = Gtk.Button(label="Choose Again…")
        btn_retry.add_css_class("suggested-action")
        btn_retry.connect("clicked", lambda b: (dialog.close(), self.open_popover.popup()))
        btn_row.append(btn_retry)

        btn_close = Gtk.Button(label="Close")
        btn_close.connect("clicked", lambda b: dialog.close())
        btn_row.append(btn_close)

        dialog.present()

    def _show_message_dialog(self, title, message, is_error=False):
        """Generic single-button dialog for errors and info messages,
        so problems are visible in the GUI and not just in the terminal."""
        dialog = Gtk.Window(transient_for=self, modal=True, title=title)
        dialog.set_default_size(360, 0)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        dialog.set_child(box)

        icon_name = "dialog-error-symbolic" if is_error else "dialog-information-symbolic"
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.append(Gtk.Image.new_from_icon_name(icon_name))
        label = Gtk.Label(label=message)
        label.set_wrap(True)
        label.set_justify(Gtk.Justification.LEFT)
        label.set_xalign(0.0)
        header.append(label)
        box.append(header)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        box.append(btn_row)

        btn_ok = Gtk.Button(label="OK")
        btn_ok.add_css_class("suggested-action")
        btn_ok.connect("clicked", lambda b: dialog.close())
        btn_row.append(btn_ok)

        dialog.present()
        return False  # for GLib.idle_add

    # --- Settings dialog ---
    def _open_settings(self):
        dialog = SettingsDialog(self)
        dialog.present()

    # --- About / keyboard shortcuts ---
    def _open_about(self):
        dialog = Gtk.Window(transient_for=self, modal=True, title="About CropFast")
        dialog.set_default_size(420, 0)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        dialog.set_child(box)

        title_label = Gtk.Label(label=f"<b>CropFast</b>  v{APP_VERSION}", use_markup=True)
        title_label.set_xalign(0.0)
        box.append(title_label)

        subtitle = Gtk.Label(label="A fast image cropping tool with aspect-ratio presets.")
        subtitle.set_xalign(0.0)
        subtitle.set_wrap(True)
        box.append(subtitle)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        shortcuts_title = Gtk.Label(label="<b>Keyboard &amp; mouse shortcuts</b>", use_markup=True)
        shortcuts_title.set_xalign(0.0)
        box.append(shortcuts_title)

        shortcuts = [
            ("Ctrl+O", "Open an image or folder"),
            ("Enter", "Crop and stay on this image"),
            ("Right-click on image", "Crop and go to the next image"),
            ("Left / Right arrow", "Previous / next image"),
            ("Mouse wheel", "Previous / next image"),
            ("F", "Switch to Freehand mode"),
            ("Esc", "Close the application"),
        ]
        grid = Gtk.Grid(row_spacing=4, column_spacing=12)
        for i, (keys, desc) in enumerate(shortcuts):
            key_label = Gtk.Label(label=keys, halign=Gtk.Align.START)
            key_label.add_css_class("dim-label")
            grid.attach(key_label, 0, i, 1, 1)
            grid.attach(Gtk.Label(label=desc, halign=Gtk.Align.START), 1, i, 1, 1)
        box.append(grid)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        btn_row.set_halign(Gtk.Align.END)
        box.append(btn_row)
        btn_close = Gtk.Button(label="Close")
        btn_close.connect("clicked", lambda b: dialog.close())
        btn_row.append(btn_close)

        dialog.present()

    def refresh_ratio_list(self):
        """Reload the ratio dropdown after settings have changed it."""
        ratios_list = [r.strip() for r in self.config.get('Crop', 'ratios', fallback='3:2, 4:3, 16:9').split(',') if r.strip()]
        self.ratio_store = Gtk.StringList.new(ratios_list)
        self.combo_ratio.set_model(self.ratio_store)
        try:
            sel_idx = ratios_list.index(self.current_ratio_str)
            self.combo_ratio.set_selected(sel_idx)
        except ValueError:
            if ratios_list:
                self.combo_ratio.set_selected(0)
                self.current_ratio_str = ratios_list[0]

    # --- Size entry fields ---
    def _add_entry_focus_watch(self, entry, which):
        """When focus leaves the field, apply the value
        (clicking outside the field also confirms the change)."""
        ctrl = Gtk.EventControllerFocus.new()
        ctrl.connect("leave", lambda c: self._apply_entry_size(which))
        entry.add_controller(ctrl)

    def _sync_size_entries(self, force=False):
        """Overwrites the fields with the current selection dimensions.
        Without force, a focused field is not overwritten (protects typing).
        force=True is used on structural changes (mode change,
        loading an image, selection reset) – overwrites ALL fields."""
        if not hasattr(self, 'entry_w'):
            return

        w_text = str(self.crop_w) if self.has_selection else ""
        h_text = str(self.crop_h) if self.has_selection else ""

        self._updating_entries = True
        if force or (not self.entry_w.has_focus() and self._cache_w != w_text):
            self.entry_w.set_text(w_text)
            self._cache_w = w_text
        if force or (not self.entry_h.has_focus() and self._cache_h != h_text):
            self.entry_h.set_text(h_text)
            self._cache_h = h_text
        self._updating_entries = False

    def _apply_entry_size(self, which):
        """Applies the value from the given field ('w' or 'h').
        With a locked ratio (ratio/portrait/landscape/auto) the other
        dimension is computed from the ratio. In freehand only the
        edited dimension changes. The change is centered – the selection
        stays around the same center point."""
        if not self.orig_pixbuf:
            return

        entry = self.entry_w if which == 'w' else self.entry_h
        try:
            val = int(round(float(entry.get_text().strip().replace(',', '.'))))
        except ValueError:
            # Non-numeric input – restore the currently displayed values
            self._sync_size_entries(force=True)
            return

        locked = self.mode in ('portrait', 'landscape', 'auto')

        # Base dimensions and center
        if self.has_selection:
            w, h = float(self.crop_w), float(self.crop_h)
            cx = self.crop_x + self.crop_w / 2.0
            cy = self.crop_y + self.crop_h / 2.0
        else:
            w, h = float(self.orig_w), float(self.orig_h)
            cx = self.orig_w / 2.0
            cy = self.orig_h / 2.0

        if locked:
            parsed = parse_ratio(self.current_ratio_str)
            if parsed:
                aspect = parsed[0] / parsed[1]
            elif h:
                aspect = w / h
            else:
                aspect = 1.5

            if which == 'w':
                w = val
                h = w / aspect
            else:
                h = val
                w = h * aspect

            # Fit to image size while keeping the ratio
            if w > self.orig_w:
                w = self.orig_w
                h = w / aspect
            if h > self.orig_h:
                h = self.orig_h
                w = h * aspect
            w = max(self.MIN_CROP, w)
            h = max(self.MIN_CROP, h)
        else:
            # Freehand – only the edited dimension changes
            if which == 'w':
                w = val
            else:
                h = val
            w = min(max(self.MIN_CROP, w), self.orig_w)
            h = min(max(self.MIN_CROP, h), self.orig_h)

        x = cx - w / 2.0
        y = cy - h / 2.0
        x, y, w, h = self._clamp_rect_to_image(x, y, w, h)

        self.crop_x, self.crop_y = int(round(x)), int(round(y))
        self.crop_w, self.crop_h = max(1, int(round(w))), max(1, int(round(h)))
        self.has_selection = True

        self._sync_size_entries(force=True)
        self.area.queue_draw()

    # --- Mode management ---
    def _update_mode_buttons(self):
        """Highlights the active mode's button (blue suggested-action style)."""
        for btn, m in ((self.btn_portrait, 'portrait'),
                       (self.btn_landscape, 'landscape'),
                       (self.btn_auto, 'auto'),
                       (self.btn_freehand, 'freehand')):
            if self.mode == m:
                btn.add_css_class("suggested-action")
            else:
                btn.remove_css_class("suggested-action")

    def set_mode(self, mode):
        """Switches the active mode. Activating the same mode again
        does nothing (so freehand can't be toggled off by clicking)."""
        if mode not in ('portrait', 'landscape', 'auto', 'freehand'):
            return
        if mode == self.mode:
            return

        # Stop editing the fields – shortcuts work immediately after switching
        # mode, and the fields may be force-overwritten with new values
        if isinstance(self.get_focus(), Gtk.Editable):
            self.set_focus(None)

        self.mode = mode
        self._update_mode_buttons()

        if mode == 'freehand':
            # No preset selection – fields must be EMPTY
            self.has_selection = False
            self.crop_w = 0
            self.crop_h = 0
            self._sync_size_entries(force=True)
        elif mode == 'portrait':
            self._orient_ratio(to_portrait=True)
        elif mode == 'landscape':
            self._orient_ratio(to_landscape=True)
        elif mode == 'auto':
            self._apply_auto_orientation()

        self.area.queue_draw()

    def _orient_ratio(self, to_portrait=False, to_landscape=False):
        """Rotates the current ratio into the requested orientation and sets the selection."""
        parsed = parse_ratio(self.current_ratio_str)
        if not parsed:
            return
        w, h = parsed
        if to_portrait and w > h:
            w, h = h, w
        elif to_landscape and h > w:
            w, h = h, w

        new_ratio_str = f"{int(w) if w.is_integer() else w}:{int(h) if h.is_integer() else h}"
        self.current_ratio_str = new_ratio_str
        self.reset_crop_box(new_ratio_str)

    def _apply_auto_orientation(self):
        """Sets the selection according to the current image's orientation."""
        if not self.orig_pixbuf:
            return
        if self.orig_h > self.orig_w:
            self._orient_ratio(to_portrait=True)
        else:
            self._orient_ratio(to_landscape=True)

    def _apply_startup_mode(self):
        """Applies the startup mode saved in the config
        (startup_mode = portrait / landscape / auto / freehand)."""
        if not self.orig_pixbuf:
            return
        mode = self.startup_mode if self.startup_mode in ('portrait', 'landscape', 'auto', 'freehand') else 'auto'
        self.set_mode(mode)

    def _resolve_initial_path(self, arg):
        def_input_str = self.config.get('Paths', 'default_input_folder', fallback='').strip()
        target_dir = Path(os.path.expandvars(def_input_str)).expanduser() if def_input_str else None
        start_file = None

        if arg:
            p = Path(arg).expanduser().resolve()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                start_file = p
                target_dir = p.parent
            elif p.is_dir():
                target_dir = p

        if target_dir is None:
            # No input folder configured yet, and nothing was passed on the
            # command line — show the empty-state placeholder instead of
            # guessing a folder.
            self.files = []
            self.current_index = -1
            return

        sort_by = self.config.get('Sorting', 'sort_by', fallback='name').lower()
        sort_order = self.config.get('Sorting', 'sort_order', fallback='ascending').lower()
        reverse = (sort_order == 'descending')

        try:
            all_files = [f for f in target_dir.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
        except OSError as e:
            print(f"Error reading folder {target_dir}: {e}", file=sys.stderr)
            # Deferred: at this point (called from __init__) the window may
            # not be presented yet, so schedule the dialog for right after.
            GLib.idle_add(
                self._show_message_dialog,
                "Couldn't Read Folder",
                f"“{target_dir}” could not be read:\n{e}",
                True
            )
            all_files = []
        if sort_by == 'name':
            all_files.sort(key=lambda f: f.name.lower(), reverse=reverse)
        else:
            all_files.sort(key=lambda f: f.stat().st_mtime, reverse=reverse)

        self.files = all_files
        if start_file and start_file in self.files:
            self.current_index = self.files.index(start_file)
        elif self.files:
            self.current_index = 0
        else:
            self.current_index = -1

    def load_current_image(self):
        if not self.files or self.current_index < 0 or self.current_index >= len(self.files):
            return

        self.image_path = self.files[self.current_index]
        self.set_title(f"CropFast – {self.image_path.name} ({self.current_index + 1}/{len(self.files)})")

        try:
            self.orig_pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(self.image_path))
            self.orig_pixbuf = self.orig_pixbuf.apply_embedded_orientation()
            self.orig_w = self.orig_pixbuf.get_width()
            self.orig_h = self.orig_pixbuf.get_height()
            self.reset_crop_box()
            # Auto mode: the selection adapts to the orientation of EVERY newly loaded image
            if self.mode == 'auto':
                self._apply_auto_orientation()
            self._sync_size_entries(force=True)   # new image = force-update the fields
            self.area.queue_draw()
        except Exception as e:
            print(f"Error loading file {self.image_path}: {e}", file=sys.stderr)
            self._show_message_dialog(
                "Couldn't Open Image",
                f"“{self.image_path.name}” could not be opened:\n{e}",
                is_error=True
            )

    def reset_crop_box(self, ratio_str=None):
        if not self.orig_pixbuf:
            return

        # In freehand mode the selection is not preset – fields stay empty
        if self.freehand_mode:
            self.has_selection = False
            self.crop_w = 0
            self.crop_h = 0
            self._sync_size_entries(force=True)
            self.area.queue_draw()
            return

        self.has_selection = True

        if ratio_str is None:
            ratio_str = self.current_ratio_str

        parsed = parse_ratio(ratio_str)
        if parsed is None:
            parsed = (3.0, 2.0)

        target_w, target_h = parsed
        target_aspect = target_w / target_h
        img_aspect = self.orig_w / self.orig_h

        if img_aspect > target_aspect:
            self.crop_h = self.orig_h
            self.crop_w = int(round(self.crop_h * target_aspect))
        else:
            self.crop_w = self.orig_w
            self.crop_h = int(round(self.crop_w / target_aspect))

        self.crop_x = (self.orig_w - self.crop_w) // 2
        self.crop_y = (self.orig_h - self.crop_h) // 2
        self._sync_size_entries(force=True)
        self.area.queue_draw()

    def navigate_image(self, delta):
        if not self.files:
            return
        self.current_index = (self.current_index + delta) % len(self.files)
        self.load_current_image()

    def on_ratio_combo_changed(self, dropdown, param):
        item = dropdown.get_selected_item()
        if not item:
            return
        val = item.get_string()
        self.current_ratio_str = val
        self.config['Crop']['current_ratio'] = val
        save_config(self.config)

        # The mode is kept – the new ratio is applied according to the active mode
        if self.mode == 'portrait':
            self._orient_ratio(to_portrait=True)
        elif self.mode == 'landscape':
            self._orient_ratio(to_landscape=True)
        elif self.mode == 'auto':
            self._apply_auto_orientation()
        elif self.mode == 'freehand':
            # The drawn selection stays; the new ratio is used next time
            pass

    # --- Drawing and calculations ---
    def _scale_factor(self):
        aw = self.area.get_width()
        ah = self.area.get_height()
        if aw <= 1 or ah <= 1 or not self.orig_pixbuf:
            return 1.0, 0, 0, 1, 1
        scale = min(aw / self.orig_w, ah / self.orig_h)
        disp_w = int(self.orig_w * scale)
        disp_h = int(self.orig_h * scale)
        ox = (aw - disp_w) // 2
        oy = (ah - disp_h) // 2
        return scale, ox, oy, disp_w, disp_h

    def _draw_thirds_grid(self, cr, rx, ry, rw, rh):
        """Rule-of-thirds grid – a dark line under a light one for contrast
        against any background."""
        points_v = [rx + rw / 3, rx + 2 * rw / 3]
        points_h = [ry + rh / 3, ry + 2 * rh / 3]

        # Dark "shadow" line
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.set_line_width(2.0)
        cr.new_path()
        for gx in points_v:
            cr.move_to(gx, ry)
            cr.line_to(gx, ry + rh)
        for gy in points_h:
            cr.move_to(rx, gy)
            cr.line_to(rx + rw, gy)
        cr.stroke()

        # Light line on top of it
        cr.set_source_rgba(1, 1, 1, 0.75)
        cr.set_line_width(1.0)
        cr.new_path()
        for gx in points_v:
            cr.move_to(gx, ry)
            cr.line_to(gx, ry + rh)
        for gy in points_h:
            cr.move_to(rx, gy)
            cr.line_to(rx + rw, gy)
        cr.stroke()

    def _draw_empty_state(self, cr, width, height):
        """Placeholder shown when no image is loaded yet (e.g. empty
        input folder, or before anything has been opened)."""
        cr.set_source_rgb(0.1, 0.1, 0.1)
        cr.paint()

        cr.set_source_rgba(1, 1, 1, 0.75)

        cr.select_font_face("Sans", 0, 1)  # normal slant, bold weight
        cr.set_font_size(20)
        main_text = "Start by opening an image or a folder"
        extents = cr.text_extents(main_text)
        cr.move_to(width / 2 - extents.width / 2 - extents.x_bearing,
                   height / 2 - 10)
        cr.show_text(main_text)

        cr.set_source_rgba(1, 1, 1, 0.5)
        cr.select_font_face("Sans", 0, 0)  # normal slant, normal weight
        cr.set_font_size(14)
        hint_text = "Open button (top left) or Ctrl+O"
        extents = cr.text_extents(hint_text)
        cr.move_to(width / 2 - extents.width / 2 - extents.x_bearing,
                   height / 2 + 16)
        cr.show_text(hint_text)

    def on_draw(self, area, cr, width, height):
        if not self.orig_pixbuf:
            self._draw_empty_state(cr, width, height)
            return

        # Live sync of the fields (a focused field is not overwritten)
        self._sync_size_entries()

        scale, ox, oy, dw, dh = self._scale_factor()

        cr.set_source_rgb(0.1, 0.1, 0.1)
        cr.paint()

        cr.save()
        cr.translate(ox, oy)
        cr.scale(scale, scale)
        Gdk.cairo_set_source_pixbuf(cr, self.orig_pixbuf, 0, 0)
        cr.paint()
        cr.restore()

        # Freehand without a selection – don't darken or draw anything
        if not self.has_selection:
            return

        cr.set_source_rgba(0, 0, 0, 0.55)
        cr.rectangle(0, 0, width, height)
        rx = ox + self.crop_x * scale
        ry = oy + self.crop_y * scale
        rw = self.crop_w * scale
        rh = self.crop_h * scale
        cr.rectangle(rx, ry, rw, rh)
        cr.set_fill_rule(1)
        cr.fill()

        cr.set_source_rgb(1.0, 0.85, 0.1)
        cr.set_line_width(2.0)
        cr.rectangle(rx, ry, rw, rh)
        cr.stroke()

        # Rule-of-thirds grid – only while actively dragging
        if self.drag_mode is not None:
            self._draw_thirds_grid(cr, rx, ry, rw, rh)

        # Handles: all 8 in freehand, only the corners in ratio-locked modes
        self._draw_handles(cr, rx, ry, rw, rh, corners_only=not self.freehand_mode)

    def _draw_handles(self, cr, rx, ry, rw, rh, corners_only=False):
        half = 9
        if corners_only:
            points = [
                (rx, ry), (rx + rw, ry), (rx, ry + rh), (rx + rw, ry + rh),
            ]
        else:
            points = [
                (rx, ry), (rx + rw, ry), (rx, ry + rh), (rx + rw, ry + rh),
                (rx + rw / 2, ry), (rx + rw / 2, ry + rh),
                (rx, ry + rh / 2), (rx + rw, ry + rh / 2),
            ]
        for px, py in points:
            cr.set_source_rgba(0, 0, 0, 0.75)
            cr.rectangle(px - half, py - half, half * 2, half * 2)
            cr.fill()
            cr.set_source_rgb(1.0, 0.85, 0.1)
            inner = half - 3
            cr.rectangle(px - inner, py - inner, inner * 2, inner * 2)
            cr.fill()

    def _hit_test(self, sx, sy, rx, ry, rw, rh):
        m = self.HANDLE_MARGIN
        near_left = abs(sx - rx) <= m
        near_right = abs(sx - (rx + rw)) <= m
        near_top = abs(sy - ry) <= m
        near_bottom = abs(sy - (ry + rh)) <= m
        within_x = rx - m <= sx <= rx + rw + m
        within_y = ry - m <= sy <= ry + rh + m

        if near_left and near_top and within_x and within_y: return 'corner-TL'
        if near_right and near_top and within_x and within_y: return 'corner-TR'
        if near_left and near_bottom and within_x and within_y: return 'corner-BL'
        if near_right and near_bottom and within_x and within_y: return 'corner-BR'
        if near_left and ry <= sy <= ry + rh: return 'edge-left'
        if near_right and ry <= sy <= ry + rh: return 'edge-right'
        if near_top and rx <= sx <= rx + rw: return 'edge-top'
        if near_bottom and rx <= sx <= rx + rw: return 'edge-bottom'
        if rx <= sx <= rx + rw and ry <= sy <= ry + rh: return 'move'
        return None

    def _update_hover_cursor(self, x, y):
        """Sets the mouse cursor according to its position over the selection (no dragging)."""
        name = None
        if self.orig_pixbuf and self.has_selection:
            scale, ox, oy, _, _ = self._scale_factor()
            rx = ox + self.crop_x * scale
            ry = oy + self.crop_y * scale
            rw = self.crop_w * scale
            rh = self.crop_h * scale
            hit = self._hit_test(x, y, rx, ry, rw, rh)

            corner_cursors = {
                'corner-TL': 'nw-resize',
                'corner-TR': 'ne-resize',
                'corner-BL': 'sw-resize',
                'corner-BR': 'se-resize',
            }
            if hit in corner_cursors:
                name = corner_cursors[hit]
            elif hit == 'move':
                name = 'move'
            elif self.freehand_mode and hit is not None:
                edge_cursors = {
                    'edge-left': 'ew-resize', 'edge-right': 'ew-resize',
                    'edge-top': 'ns-resize', 'edge-bottom': 'ns-resize',
                }
                name = edge_cursors.get(hit)

        self.area.set_cursor_from_name(name)

    def _fit_size_to_image(self, w, h, aspect):
        if w > self.orig_w:
            w = self.orig_w
            h = w / aspect
        if h > self.orig_h:
            h = self.orig_h
            w = h * aspect
        return max(self.MIN_CROP, w), max(self.MIN_CROP, h)

    def _clamp_rect_to_image(self, x, y, w, h):
        w = min(w, self.orig_w)
        h = min(h, self.orig_h)
        x = max(0, min(x, self.orig_w - w))
        y = max(0, min(y, self.orig_h - h))
        return x, y, w, h

    def _resize_crop(self, mode, img_x, img_y, start_cx, start_cy, start_cw, start_ch):
        aspect = start_cw / start_ch
        if mode == 'corner-BR':
            ax, ay = start_cx, start_cy
            raw_w, raw_h = img_x - ax, img_y - ay
        elif mode == 'corner-TL':
            ax, ay = start_cx + start_cw, start_cy + start_ch
            raw_w, raw_h = ax - img_x, ay - img_y
        elif mode == 'corner-TR':
            ax, ay = start_cx, start_cy + start_ch
            raw_w, raw_h = img_x - ax, ay - img_y
        elif mode == 'corner-BL':
            ax, ay = start_cx + start_cw, start_cy
            raw_w, raw_h = ax - img_x, img_y - ay
        elif mode == 'edge-right':
            ax = start_cx
            raw_w = img_x - ax
        elif mode == 'edge-left':
            ax = start_cx + start_cw
            raw_w = ax - img_x
        elif mode == 'edge-bottom':
            ay = start_cy
            raw_h = img_y - ay
        elif mode == 'edge-top':
            ay = start_cy + start_ch
            raw_h = ay - img_y
        else:
            return

        if mode.startswith('corner'):
            raw_w = max(raw_w, self.MIN_CROP)
            raw_h = max(raw_h, self.MIN_CROP)
            if raw_w / raw_h > aspect:
                new_h = raw_h
                new_w = new_h * aspect
            else:
                new_w = raw_w
                new_h = new_w / aspect
            new_w, new_h = self._fit_size_to_image(new_w, new_h, aspect)

            if mode == 'corner-BR': new_x, new_y = ax, ay
            elif mode == 'corner-TL': new_x, new_y = ax - new_w, ay - new_h
            elif mode == 'corner-TR': new_x, new_y = ax, ay - new_h
            else: new_x, new_y = ax - new_w, ay

            new_x, new_y, new_w, new_h = self._clamp_rect_to_image(new_x, new_y, new_w, new_h)

        elif mode in ('edge-right', 'edge-left'):
            new_h = start_ch
            new_y = start_cy
            if mode == 'edge-right':
                max_w = max(self.MIN_CROP, self.orig_w - ax)
                new_w = min(max(raw_w, self.MIN_CROP), max_w)
                new_x = ax
            else:
                max_w = max(self.MIN_CROP, ax)
                new_w = min(max(raw_w, self.MIN_CROP), max_w)
                new_x = ax - new_w

        else:  # edge-bottom / edge-top
            new_w = start_cw
            new_x = start_cx
            if mode == 'edge-bottom':
                max_h = max(self.MIN_CROP, self.orig_h - ay)
                new_h = min(max(raw_h, self.MIN_CROP), max_h)
                new_y = ay
            else:
                max_h = max(self.MIN_CROP, ay)
                new_h = min(max(raw_h, self.MIN_CROP), max_h)
                new_y = ay - new_h

        self.crop_x, self.crop_y = int(round(new_x)), int(round(new_y))
        self.crop_w, self.crop_h = max(1, int(round(new_w))), max(1, int(round(new_h)))

    def on_press(self, gesture, n_press, x, y):
        # Clicking on the canvas ends editing of the fields (a leave event applies the value)
        if isinstance(self.get_focus(), Gtk.Editable):
            self.set_focus(None)

        scale, ox, oy, _, _ = self._scale_factor()

        if self.freehand_mode:
            hit = None
            if self.has_selection:
                rx = ox + self.crop_x * scale
                ry = oy + self.crop_y * scale
                rw = self.crop_w * scale
                rh = self.crop_h * scale
                hit = self._hit_test(x, y, rx, ry, rw, rh)

            if hit is None:
                # Start drawing a new selection with the left button
                img_x = max(0.0, min((x - ox) / scale, float(self.orig_w)))
                img_y = max(0.0, min((y - oy) / scale, float(self.orig_h)))
                self.drag_mode = 'draw'
                self.drag_start = (img_x, img_y)   # anchor in image coordinates
                self.crop_x = int(round(img_x))
                self.crop_y = int(round(img_y))
                self.crop_w = 0
                self.crop_h = 0
                self.has_selection = True
                self.area.queue_draw()
            else:
                # Grabbing an existing selection (move / resize)
                self.drag_mode = hit
                self.drag_start = (x, y, self.crop_x, self.crop_y, self.crop_w, self.crop_h)
            return

        # Ratio-locked modes (ratio/portrait/landscape/auto):
        # corner = resize while keeping the ratio, inside = move
        hit = None
        if self.has_selection:
            rx = ox + self.crop_x * scale
            ry = oy + self.crop_y * scale
            rw = self.crop_w * scale
            rh = self.crop_h * scale
            hit = self._hit_test(x, y, rx, ry, rw, rh)

        if hit is not None and hit.startswith('corner'):
            self.drag_mode = hit
            self.drag_start = (x, y, self.crop_x, self.crop_y, self.crop_w, self.crop_h)
            return

        img_x = (x - ox) / scale
        img_y = (y - oy) / scale

        if (self.crop_x <= img_x <= self.crop_x + self.crop_w and
                self.crop_y <= img_y <= self.crop_y + self.crop_h):
            self.drag_mode = 'move'
            self.drag_start = (x, y, self.crop_x, self.crop_y, self.crop_w, self.crop_h)

    def on_release(self, gesture, n_press, x, y):
        if self.drag_mode == 'draw':
            # A selection that's too small (e.g. just a click) is discarded
            if self.crop_w < self.MIN_CROP or self.crop_h < self.MIN_CROP:
                self.has_selection = False
                self.crop_w = 0
                self.crop_h = 0
        self.drag_start = None
        self.drag_mode = None
        self.area.queue_draw()

    def on_motion(self, controller, x, y):
        if self.drag_start is None or self.drag_mode is None:
            # Not dragging – just update the cursor based on position
            self._update_hover_cursor(x, y)
            return
        scale, ox, oy, _, _ = self._scale_factor()

        # Drawing a new selection in freehand mode
        if self.drag_mode == 'draw':
            ax, ay = self.drag_start
            img_x = max(0.0, min((x - ox) / scale, float(self.orig_w)))
            img_y = max(0.0, min((y - oy) / scale, float(self.orig_h)))
            x0, x1 = sorted((ax, img_x))
            y0, y1 = sorted((ay, img_y))
            self.crop_x = int(round(x0))
            self.crop_y = int(round(y0))
            self.crop_w = max(1, int(round(x1 - x0)))
            self.crop_h = max(1, int(round(y1 - y0)))
            self.area.queue_draw()
            return

        start_x, start_y, start_cx, start_cy, start_cw, start_ch = self.drag_start

        if self.drag_mode == 'move':
            dx = (x - start_x) / scale
            dy = (y - start_y) / scale
            new_x = max(0, min(start_cx + dx, self.orig_w - self.crop_w))
            new_y = max(0, min(start_cy + dy, self.orig_h - self.crop_h))
            self.crop_x, self.crop_y = int(round(new_x)), int(round(new_y))
            self.area.queue_draw()
            return

        img_x = (x - ox) / scale
        img_y = (y - oy) / scale
        self._resize_crop(self.drag_mode, img_x, img_y, start_cx, start_cy, start_cw, start_ch)
        self.area.queue_draw()

    def on_scroll(self, controller, dx, dy):
        if dy > 0:
            self.navigate_image(1)
        elif dy < 0:
            self.navigate_image(-1)
        return True

    def on_key(self, controller, keyval, keycode, state):
        keyval_lower = Gdk.keyval_to_lower(keyval)

        # If a text field has focus, keys belong to it:
        # Enter = apply size ("activate" signal on Entry),
        # arrows = move the text cursor, Esc = cancel editing
        focus = self.get_focus()
        if isinstance(focus, Gtk.Editable):
            if keyval_lower == Gdk.KEY_Escape:
                self._sync_size_entries(force=True)
                self.set_focus(None)
                return True
            return False

        ctrl_pressed = bool(state & Gdk.ModifierType.CONTROL_MASK)

        if ctrl_pressed and keyval_lower == Gdk.KEY_o:
            self.open_popover.popup()
            return True
        if keyval_lower in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            # Enter – crop and STAY on this image
            self.do_crop()
            return True
        if keyval_lower == Gdk.KEY_Escape:
            self.close()
            return True
        if keyval_lower == Gdk.KEY_f:
            self.set_mode('freehand')
            return True
        if keyval_lower == Gdk.KEY_Left:
            self.navigate_image(-1)
            return True
        if keyval_lower == Gdk.KEY_Right:
            self.navigate_image(1)
            return True
        return False

    def do_crop(self, advance=False):
        if not self.orig_pixbuf or not self.image_path:
            return
        # Guard – don't crop without a valid selection
        if not self.has_selection or self.crop_w <= 1 or self.crop_h <= 1:
            return

        try:
            out_folder = Path(os.path.expandvars(self.config.get('Paths', 'output_folder', fallback=str(DEFAULT_OUTPUT_DIR)))).expanduser()
            out_folder.mkdir(parents=True, exist_ok=True)

            cropped = self.orig_pixbuf.new_subpixbuf(
                self.crop_x, self.crop_y, self.crop_w, self.crop_h
            )
            stem = self.image_path.stem
            suffix = self.image_path.suffix.lower()
            if suffix not in ('.jpg', '.jpeg', '.png', '.webp'):
                suffix = '.jpg'

            dest = out_folder / f"{stem}_crop{suffix}"
            counter = 1
            while dest.exists():
                dest = out_folder / f"{stem}_crop_{counter}{suffix}"
                counter += 1

            if suffix in ('.jpg', '.jpeg'):
                # 97 is close to visually lossless while keeping file size
                # reasonable; 100 rarely looks any better but bloats size.
                cropped.savev(str(dest), "jpeg", ["quality"], ["97"])
            elif suffix == '.png':
                cropped.savev(str(dest), "png", [], [])
            elif suffix == '.webp':
                cropped.savev(str(dest), "webp", ["quality"], ["97"])

            print(f"Cropped image saved to: {dest}")

            # Auto-advance – ONLY on right mouse click (after a successful save)
            if advance:
                self.navigate_image(1)
        except Exception as e:
            print(f"Error while cropping: {e}", file=sys.stderr)
            self._show_message_dialog(
                "Crop Failed",
                f"Couldn't save the cropped image:\n{e}",
                is_error=True
            )

class CropApplication(Gtk.Application):
    def __init__(self, initial_path=None):
        # NOTE: change this to your own reverse-domain ID before publishing,
        # e.g. "io.github.<your-username>.CropFast" — it must match the
        # "Exec"/filename used in the .desktop file for desktop integration.
        super().__init__(application_id="io.github.example.CropFast")
        self.initial_path = initial_path

    def do_activate(self):
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property("gtk-application-prefer-dark-theme", True)
        win = CropApp(self, initial_path=self.initial_path)
        win.present()

if __name__ == "__main__":
    init_arg = sys.argv[1] if len(sys.argv) > 1 else None
    app = CropApplication(initial_path=init_arg)
    app.run(None)
