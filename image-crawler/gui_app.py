"""
Google Books Crawler GUI Application
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import os
import sys
from datetime import datetime

# Add modules to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.scraper import GoogleBooksScraper
from modules.image_converter import ImageConverter
from modules.file_reorder import FileReorder
from modules.settings_manager import SettingsManager


class GoogleBooksCrawlerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Google Books Crawler GUI")

        # Initialize settings manager first
        self.settings = SettingsManager()

        # Apply initial window settings
        width = self.settings.get_int('Window', 'gui_width', 900)
        height = self.settings.get_int('Window', 'gui_height', 700)
        x = self.settings.get_int('Window', 'gui_x', 100)
        y = self.settings.get_int('Window', 'gui_y', 100)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # Initialize modules
        self.scraper = None
        self.converter = ImageConverter()
        self.reorder = FileReorder()

        # Create notebook for tabs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Create tabs
        self.create_scraper_tab()
        self.create_converter_tab()
        self.create_reorder_tab()
        self.create_pdf_tab()
        self.create_settings_tab()

        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        self.status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Check profile status on startup
        self.root.after(100, self.check_profile_status)

        # Start window position tracking
        self.is_tracking = False
        self.start_position_tracking()

        # Set up cleanup on window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_scraper_tab(self):
        """Create the scraper tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Scraper")

        # Control buttons (moved to top)
        control_frame = ttk.LabelFrame(tab, text="Browser Control", padding="10")
        control_frame.pack(fill="x", padx=10, pady=5)

        self.init_driver_btn = ttk.Button(control_frame, text="Initialize Driver", command=self.init_driver)
        self.init_driver_btn.pack(side="left", padx=5)

        self.navigate_btn = ttk.Button(control_frame, text="Navigate to Book", command=self.navigate_to_book, state="disabled")
        self.navigate_btn.pack(side="left", padx=5)

        self.start_scraping_btn = ttk.Button(control_frame, text="Start Scraping", command=self.start_scraping, state="disabled")
        self.start_scraping_btn.pack(side="left", padx=5)

        self.stop_scraping_btn = ttk.Button(control_frame, text="Stop Scraping", command=self.stop_scraping, state="disabled")
        self.stop_scraping_btn.pack(side="left", padx=5)

        ttk.Button(control_frame, text="Close Driver", command=self.close_driver).pack(side="left", padx=5)

        # URL input
        url_frame = ttk.LabelFrame(tab, text="Book URL", padding="10")
        url_frame.pack(fill="x", padx=10, pady=5)

        self.url_var = tk.StringVar(value=self.settings.get('Scraper', 'book_url', 'https://play.google.com/books/reader?id='))
        self.url_var.trace('w', lambda *args: self.settings.set('Scraper', 'book_url', self.url_var.get()))
        ttk.Label(url_frame, text="URL:").pack(side="left")
        ttk.Entry(url_frame, textvariable=self.url_var, width=70).pack(side="left", padx=5, fill="x", expand=True)

        # Download path
        path_frame = ttk.LabelFrame(tab, text="Download Path", padding="10")
        path_frame.pack(fill="x", padx=10, pady=5)

        self.download_path_var = tk.StringVar(value=self.settings.get('Scraper', 'download_path', os.path.join(os.getcwd(), "Downloads")))
        self.download_path_var.trace('w', lambda *args: self.settings.set('Scraper', 'download_path', self.download_path_var.get()))
        ttk.Label(path_frame, text="Path:").pack(side="left")
        ttk.Entry(path_frame, textvariable=self.download_path_var, width=50).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(path_frame, text="Browse", command=self.browse_download_path).pack(side="left", padx=5)

        # Start number and Next Index
        start_frame = ttk.LabelFrame(tab, text="Scraping Index", padding="10")
        start_frame.pack(fill="x", padx=10, pady=5)

        # Start number input
        ttk.Label(start_frame, text="Start Number:").pack(side="left")
        self.start_num_var = tk.IntVar(value=self.settings.get_int('Scraper', 'force_start_number', 0))
        self.start_num_var.trace('w', lambda *args: self.settings.set('Scraper', 'force_start_number', self.start_num_var.get()))
        start_spinbox = ttk.Spinbox(start_frame, from_=0, to=9999, textvariable=self.start_num_var, width=10)
        start_spinbox.pack(side="left", padx=5)

        # Separator
        ttk.Label(start_frame, text="  |  ").pack(side="left", padx=10)

        # Next index display (read-only)
        ttk.Label(start_frame, text="Next Index:").pack(side="left")
        self.next_index_var = tk.StringVar(value="0")
        next_index_entry = ttk.Entry(start_frame, textvariable=self.next_index_var, width=10, state="readonly")
        next_index_entry.pack(side="left", padx=5)

        # Apply button to use next index as start number
        ttk.Button(start_frame, text="Use as Start",
                  command=lambda: self.start_num_var.set(int(self.next_index_var.get()))).pack(side="left", padx=5)

        # Zoom controls
        zoom_frame = ttk.LabelFrame(tab, text="Zoom Control", padding="10")
        zoom_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(zoom_frame, text="Zoom Out (-)", command=self.zoom_out, width=15).pack(side="left", padx=5)
        ttk.Button(zoom_frame, text="Reset (100%)", command=self.reset_zoom, width=15).pack(side="left", padx=5)
        ttk.Button(zoom_frame, text="Zoom In (+)", command=self.zoom_in, width=15).pack(side="left", padx=5)

        ttk.Label(zoom_frame, text="Custom Zoom:").pack(side="left", padx=10)
        self.zoom_level_var = tk.IntVar(value=self.settings.get_int('Scraper', 'zoom_level', 100))
        self.zoom_level_var.trace('w', lambda *args: self.settings.set('Scraper', 'zoom_level', self.zoom_level_var.get()))
        zoom_spinbox = ttk.Spinbox(zoom_frame, from_=25, to=300, textvariable=self.zoom_level_var, width=10, increment=10)
        zoom_spinbox.pack(side="left", padx=5)
        ttk.Label(zoom_frame, text="%").pack(side="left")
        ttk.Button(zoom_frame, text="Apply", command=self.apply_zoom, width=10).pack(side="left", padx=5)

        self.zoom_status_var = tk.StringVar(value="Zoom: 100%")
        ttk.Label(zoom_frame, textvariable=self.zoom_status_var, font=("Arial", 10, "bold")).pack(side="right", padx=10)

        # Progress
        self.scraper_progress = ttk.Progressbar(tab, mode='indeterminate')
        self.scraper_progress.pack(fill="x", padx=10, pady=5)

        # Log output
        log_frame = ttk.LabelFrame(tab, text="Log", padding="10")
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.scraper_log = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD)
        self.scraper_log.pack(fill="both", expand=True)

    def create_converter_tab(self):
        """Create the converter tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="PNG Converter")

        # Directory selection
        dir_frame = ttk.LabelFrame(tab, text="Directory", padding="10")
        dir_frame.pack(fill="x", padx=10, pady=5)

        self.convert_dir_var = tk.StringVar(value=self.settings.get('Converter', 'directory', os.path.join(os.getcwd(), "Downloads")))
        self.convert_dir_var.trace('w', lambda *args: self.settings.set('Converter', 'directory', self.convert_dir_var.get()))
        ttk.Label(dir_frame, text="Directory:").pack(side="left")
        ttk.Entry(dir_frame, textvariable=self.convert_dir_var, width=50).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(dir_frame, text="Browse", command=self.browse_convert_dir).pack(side="left", padx=5)

        # Convert to PNG
        png_frame = ttk.LabelFrame(tab, text="Convert to PNG", padding="10")
        png_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(png_frame, text="Convert All to PNG", command=self.convert_to_png, width=30).pack(pady=5)

        # Convert to JPEG
        jpeg_frame = ttk.LabelFrame(tab, text="Convert PNG to JPEG", padding="10")
        jpeg_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(jpeg_frame, text="Output Directory:").grid(row=0, column=0, sticky="w")
        self.jpeg_output_var = tk.StringVar(value=self.settings.get('Converter', 'jpeg_output', ''))
        self.jpeg_output_var.trace('w', lambda *args: self.settings.set('Converter', 'jpeg_output', self.jpeg_output_var.get()))
        ttk.Entry(jpeg_frame, textvariable=self.jpeg_output_var, width=40).grid(row=0, column=1, padx=5)
        ttk.Button(jpeg_frame, text="Browse", command=self.browse_jpeg_output).grid(row=0, column=2)

        self.apply_sharpness_var = tk.BooleanVar(value=self.settings.get_bool('Converter', 'apply_sharpness', True))
        self.apply_sharpness_var.trace('w', lambda *args: self.settings.set('Converter', 'apply_sharpness', str(self.apply_sharpness_var.get())))
        ttk.Checkbutton(jpeg_frame, text="Apply Sharpness Enhancement", variable=self.apply_sharpness_var).grid(row=1, column=0, columnspan=2, pady=5)

        ttk.Button(jpeg_frame, text="Convert to JPEG", command=self.convert_to_jpeg, width=30).grid(row=2, column=0, columnspan=3, pady=5)

        # Progress
        self.converter_progress = ttk.Progressbar(tab, maximum=100)
        self.converter_progress.pack(fill="x", padx=10, pady=5)

        # Log
        log_frame = ttk.LabelFrame(tab, text="Log", padding="10")
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.converter_log = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD)
        self.converter_log.pack(fill="both", expand=True)

    def create_reorder_tab(self):
        """Create the reorder tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="File Reorder")

        # Directory selection
        dir_frame = ttk.LabelFrame(tab, text="Directory", padding="10")
        dir_frame.pack(fill="x", padx=10, pady=5)

        self.reorder_dir_var = tk.StringVar(value=self.settings.get('Reorder', 'directory', os.path.join(os.getcwd(), "Downloads")))
        self.reorder_dir_var.trace('w', lambda *args: self.settings.set('Reorder', 'directory', self.reorder_dir_var.get()))
        ttk.Label(dir_frame, text="Directory:").pack(side="left")
        ttk.Entry(dir_frame, textvariable=self.reorder_dir_var, width=50).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(dir_frame, text="Browse", command=self.browse_reorder_dir).pack(side="left", padx=5)

        # Options
        options_frame = ttk.LabelFrame(tab, text="Options", padding="10")
        options_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(options_frame, text="File Extension:").grid(row=0, column=0, sticky="w")
        self.reorder_ext_var = tk.StringVar(value=self.settings.get('Reorder', 'file_extension', '.png'))
        self.reorder_ext_var.trace('w', lambda *args: self.settings.set('Reorder', 'file_extension', self.reorder_ext_var.get()))
        ttk.Entry(options_frame, textvariable=self.reorder_ext_var, width=10).grid(row=0, column=1, padx=5)

        ttk.Label(options_frame, text="Start Number:").grid(row=1, column=0, sticky="w")
        self.reorder_start_var = tk.IntVar(value=self.settings.get_int('Reorder', 'start_number', 0))
        self.reorder_start_var.trace('w', lambda *args: self.settings.set('Reorder', 'start_number', self.reorder_start_var.get()))
        ttk.Spinbox(options_frame, from_=0, to=9999, textvariable=self.reorder_start_var, width=10).grid(row=1, column=1, padx=5)

        # Preview and execute
        button_frame = ttk.Frame(tab)
        button_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(button_frame, text="Preview Files", command=self.preview_files, width=20).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Rename Files", command=self.rename_files, width=20).pack(side="left", padx=5)

        # Progress
        self.reorder_progress = ttk.Progressbar(tab, maximum=100)
        self.reorder_progress.pack(fill="x", padx=10, pady=5)

        # File list
        list_frame = ttk.LabelFrame(tab, text="File List", padding="10")
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.file_listbox = tk.Listbox(list_frame)
        self.file_listbox.pack(fill="both", expand=True)

    def create_pdf_tab(self):
        """Create the PDF tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="PDF Creator")

        # Source directory
        source_frame = ttk.LabelFrame(tab, text="Source Directory", padding="10")
        source_frame.pack(fill="x", padx=10, pady=5)

        self.pdf_source_var = tk.StringVar(value=self.settings.get('PDF', 'source_directory', os.path.join(os.getcwd(), "Downloads")))
        self.pdf_source_var.trace('w', lambda *args: self.settings.set('PDF', 'source_directory', self.pdf_source_var.get()))
        ttk.Label(source_frame, text="Directory:").pack(side="left")
        ttk.Entry(source_frame, textvariable=self.pdf_source_var, width=50).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(source_frame, text="Browse", command=self.browse_pdf_source).pack(side="left", padx=5)

        # Output file
        output_frame = ttk.LabelFrame(tab, text="Output PDF", padding="10")
        output_frame.pack(fill="x", padx=10, pady=5)

        self.pdf_output_var = tk.StringVar(value=self.settings.get('PDF', 'output_file', os.path.join(os.getcwd(), "output.pdf")))
        self.pdf_output_var.trace('w', lambda *args: self.settings.set('PDF', 'output_file', self.pdf_output_var.get()))
        ttk.Label(output_frame, text="Output File:").pack(side="left")
        ttk.Entry(output_frame, textvariable=self.pdf_output_var, width=50).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(output_frame, text="Browse", command=self.browse_pdf_output).pack(side="left", padx=5)

        # Options
        options_frame = ttk.LabelFrame(tab, text="Options", padding="10")
        options_frame.pack(fill="x", padx=10, pady=5)

        self.enhance_color_var = tk.BooleanVar(value=self.settings.get_bool('PDF', 'enhance_color', True))
        self.enhance_color_var.trace('w', lambda *args: self.settings.set('PDF', 'enhance_color', str(self.enhance_color_var.get())))
        ttk.Checkbutton(options_frame, text="Enhance Colors", variable=self.enhance_color_var).grid(row=0, column=0, sticky="w")

        ttk.Label(options_frame, text="Color Factor:").grid(row=1, column=0, sticky="w")
        self.color_factor_var = tk.DoubleVar(value=self.settings.get_float('PDF', 'color_factor', 1.5))
        self.color_factor_var.trace('w', lambda *args: self.settings.set('PDF', 'color_factor', self.color_factor_var.get()))
        ttk.Scale(options_frame, from_=1.0, to=2.0, variable=self.color_factor_var, orient="horizontal", length=200).grid(row=1, column=1, padx=5)
        ttk.Label(options_frame, textvariable=self.color_factor_var).grid(row=1, column=2)

        # Create PDF button
        ttk.Button(tab, text="Create PDF", command=self.create_pdf, width=30).pack(pady=10)

        # Progress
        self.pdf_progress = ttk.Progressbar(tab, maximum=100)
        self.pdf_progress.pack(fill="x", padx=10, pady=5)

        # Log
        log_frame = ttk.LabelFrame(tab, text="Log", padding="10")
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.pdf_log = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD)
        self.pdf_log.pack(fill="both", expand=True)

    def create_settings_tab(self):
        """Create the settings tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Settings")

        # Chrome Profile Settings (moved from Scraper tab)
        profile_frame = ttk.LabelFrame(tab, text="Chrome Profile Settings", padding="10")
        profile_frame.pack(fill="x", padx=10, pady=5)

        self.use_profile_var = tk.BooleanVar(value=self.settings.get_bool('Scraper', 'use_profile', True))
        profile_checkbox = ttk.Checkbutton(
            profile_frame,
            text="Use persistent Chrome profile (keeps login sessions)",
            variable=self.use_profile_var,
            command=self.on_profile_toggle
        )
        profile_checkbox.pack(side="left", padx=5)

        self.profile_status_var = tk.StringVar(value="")
        ttk.Label(profile_frame, textvariable=self.profile_status_var, foreground="green").pack(side="left", padx=20)

        ttk.Button(profile_frame, text="Clear Profile", command=self.clear_profile).pack(side="right", padx=5)

        # Current Position Display
        current_frame = ttk.LabelFrame(tab, text="Current Window Positions (Live)", padding="10")
        current_frame.pack(fill="x", padx=10, pady=5)

        # GUI current position display
        self.gui_current_label = ttk.Label(current_frame, text="GUI Window: Position (0, 0) Size: 0x0",
                                          font=("Consolas", 10, "bold"), foreground="blue")
        self.gui_current_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Button(current_frame, text="Apply to GUI Settings",
                  command=self.apply_current_gui_position).grid(row=0, column=1, padx=5, pady=2)

        # Browser current position display
        self.browser_current_label = ttk.Label(current_frame, text="Browser: Not initialized",
                                               font=("Consolas", 10, "bold"), foreground="green")
        self.browser_current_label.grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Button(current_frame, text="Apply to Browser Settings",
                  command=self.apply_current_browser_position).grid(row=1, column=1, padx=5, pady=2)

        # GUI Window Settings
        gui_frame = ttk.LabelFrame(tab, text="GUI Window Settings", padding="10")
        gui_frame.pack(fill="x", padx=10, pady=5)

        # GUI initial position and size
        ttk.Label(gui_frame, text="Initial Position (x, y):").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.gui_x_var = tk.IntVar(value=self.settings.get_int('Window', 'gui_x', 100))
        self.gui_y_var = tk.IntVar(value=self.settings.get_int('Window', 'gui_y', 100))
        self.gui_x_var.trace('w', lambda *args: self.settings.set('Window', 'gui_x', self.gui_x_var.get()))
        self.gui_y_var.trace('w', lambda *args: self.settings.set('Window', 'gui_y', self.gui_y_var.get()))

        ttk.Spinbox(gui_frame, from_=0, to=3000, textvariable=self.gui_x_var, width=10).grid(row=0, column=1, padx=2, pady=2)
        ttk.Label(gui_frame, text="x").grid(row=0, column=2, padx=2, pady=2)
        ttk.Spinbox(gui_frame, from_=0, to=2000, textvariable=self.gui_y_var, width=10).grid(row=0, column=3, padx=2, pady=2)

        ttk.Label(gui_frame, text="Initial Size (width, height):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.gui_width_var = tk.IntVar(value=self.settings.get_int('Window', 'gui_width', 900))
        self.gui_height_var = tk.IntVar(value=self.settings.get_int('Window', 'gui_height', 700))
        self.gui_width_var.trace('w', lambda *args: self.settings.set('Window', 'gui_width', self.gui_width_var.get()))
        self.gui_height_var.trace('w', lambda *args: self.settings.set('Window', 'gui_height', self.gui_height_var.get()))

        ttk.Spinbox(gui_frame, from_=600, to=1920, textvariable=self.gui_width_var, width=10, increment=10).grid(row=1, column=1, padx=2, pady=2)
        ttk.Label(gui_frame, text="x").grid(row=1, column=2, padx=2, pady=2)
        ttk.Spinbox(gui_frame, from_=400, to=1080, textvariable=self.gui_height_var, width=10, increment=10).grid(row=1, column=3, padx=2, pady=2)

        ttk.Button(gui_frame, text="Apply to Current Window", command=self.apply_gui_settings).grid(row=0, column=4, rowspan=2, padx=10, pady=2)

        # GUI position after browser opens
        ttk.Label(gui_frame, text="Position After Browser Opens (x, y):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.gui_after_x_var = tk.IntVar(value=self.settings.get_int('Window', 'gui_after_browser_x', 50))
        self.gui_after_y_var = tk.IntVar(value=self.settings.get_int('Window', 'gui_after_browser_y', 50))
        self.gui_after_x_var.trace('w', lambda *args: self.settings.set('Window', 'gui_after_browser_x', self.gui_after_x_var.get()))
        self.gui_after_y_var.trace('w', lambda *args: self.settings.set('Window', 'gui_after_browser_y', self.gui_after_y_var.get()))

        ttk.Spinbox(gui_frame, from_=0, to=3000, textvariable=self.gui_after_x_var, width=10).grid(row=2, column=1, padx=2, pady=2)
        ttk.Label(gui_frame, text="x").grid(row=2, column=2, padx=2, pady=2)
        ttk.Spinbox(gui_frame, from_=0, to=2000, textvariable=self.gui_after_y_var, width=10).grid(row=2, column=3, padx=2, pady=2)

        # Browser Window Settings
        browser_frame = ttk.LabelFrame(tab, text="Browser Window Settings", padding="10")
        browser_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(browser_frame, text="Browser Position (x, y):").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.browser_x_var = tk.IntVar(value=self.settings.get_int('Window', 'browser_x', 500))
        self.browser_y_var = tk.IntVar(value=self.settings.get_int('Window', 'browser_y', 100))
        self.browser_x_var.trace('w', lambda *args: self.settings.set('Window', 'browser_x', self.browser_x_var.get()))
        self.browser_y_var.trace('w', lambda *args: self.settings.set('Window', 'browser_y', self.browser_y_var.get()))

        ttk.Spinbox(browser_frame, from_=0, to=3000, textvariable=self.browser_x_var, width=10).grid(row=0, column=1, padx=2, pady=2)
        ttk.Label(browser_frame, text="x").grid(row=0, column=2, padx=2, pady=2)
        ttk.Spinbox(browser_frame, from_=0, to=2000, textvariable=self.browser_y_var, width=10).grid(row=0, column=3, padx=2, pady=2)

        ttk.Label(browser_frame, text="Browser Size (width, height):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.browser_width_var = tk.IntVar(value=self.settings.get_int('Window', 'browser_width', 1200))
        self.browser_height_var = tk.IntVar(value=self.settings.get_int('Window', 'browser_height', 800))
        self.browser_width_var.trace('w', lambda *args: self.settings.set('Window', 'browser_width', self.browser_width_var.get()))
        self.browser_height_var.trace('w', lambda *args: self.settings.set('Window', 'browser_height', self.browser_height_var.get()))

        ttk.Spinbox(browser_frame, from_=800, to=1920, textvariable=self.browser_width_var, width=10, increment=10).grid(row=1, column=1, padx=2, pady=2)
        ttk.Label(browser_frame, text="x").grid(row=1, column=2, padx=2, pady=2)
        ttk.Spinbox(browser_frame, from_=600, to=1080, textvariable=self.browser_height_var, width=10, increment=10).grid(row=1, column=3, padx=2, pady=2)

        # Preset buttons
        preset_frame = ttk.LabelFrame(tab, text="Window Presets", padding="10")
        preset_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(preset_frame, text="Side by Side", command=self.preset_side_by_side).pack(side="left", padx=5)
        ttk.Button(preset_frame, text="Top and Bottom", command=self.preset_top_bottom).pack(side="left", padx=5)
        ttk.Button(preset_frame, text="Default", command=self.preset_default).pack(side="left", padx=5)
        ttk.Button(preset_frame, text="Get Current Positions", command=self.get_current_positions).pack(side="left", padx=5)

        # Info
        info_frame = ttk.LabelFrame(tab, text="Information", padding="10")
        info_frame.pack(fill="x", padx=10, pady=5)

        info_text = """Window position and size settings:
- GUI Initial: Position and size when the application starts
- GUI After Browser: GUI window moves here after browser opens
- Browser Settings: Applied when Initialize Driver is clicked
- Use presets for common layouts or get current positions"""

        ttk.Label(info_frame, text=info_text, justify="left", wraplength=600).pack(padx=5, pady=5)

    # Scraper methods
    def init_driver(self):
        """Initialize Chrome driver"""
        self.check_profile_status()
        use_profile = self.use_profile_var.get()

        if use_profile:
            self.log_message(self.scraper_log, "Initializing Chrome driver with persistent profile...")
        else:
            self.log_message(self.scraper_log, "Initializing Chrome driver without profile...")

        self.scraper = GoogleBooksScraper(self.download_path_var.get(), use_profile=use_profile)

        # Get browser window settings
        browser_width = self.settings.get_int('Window', 'browser_width', 1200)
        browser_height = self.settings.get_int('Window', 'browser_height', 800)
        browser_x = self.settings.get_int('Window', 'browser_x', 500)
        browser_y = self.settings.get_int('Window', 'browser_y', 100)

        if self.scraper.init_driver(
            use_existing_profile=use_profile,
            window_size=(browser_width, browser_height),
            window_position=(browser_x, browser_y)
        ):
            self.log_message(self.scraper_log, "Driver initialized successfully")
            self.log_message(self.scraper_log, f"Browser positioned at ({browser_x}, {browser_y}) with size {browser_width}x{browser_height}")
            if use_profile:
                self.log_message(self.scraper_log, "Profile loaded - previous login sessions should be preserved")

            # Move GUI window to "after browser" position
            gui_after_x = self.settings.get_int('Window', 'gui_after_browser_x', 50)
            gui_after_y = self.settings.get_int('Window', 'gui_after_browser_y', 50)
            self.root.geometry(f"+{gui_after_x}+{gui_after_y}")
            self.log_message(self.scraper_log, f"GUI moved to ({gui_after_x}, {gui_after_y})")

            self.navigate_btn.config(state="normal")
            self.start_scraping_btn.config(state="normal")  # Enable Start Scraping immediately
            self.init_driver_btn.config(state="disabled")
        else:
            self.log_message(self.scraper_log, "Failed to initialize driver")

    def navigate_to_book(self):
        """Navigate to book URL"""
        if not self.scraper:
            return

        url = self.url_var.get()
        self.log_message(self.scraper_log, f"Navigating to: {url}")

        if self.scraper.navigate_to_book(url):
            self.log_message(self.scraper_log, "Navigation successful. Please login if required.")
            self.start_scraping_btn.config(state="normal")
        else:
            self.log_message(self.scraper_log, "Navigation failed")

    def start_scraping(self):
        """Start scraping in a separate thread"""
        if not self.scraper:
            return

        # If no URL has been navigated to, navigate to the current URL
        if not self.scraper.driver.current_url or self.scraper.driver.current_url == "data:,":
            url = self.url_var.get()
            self.log_message(self.scraper_log, f"Navigating to: {url}")
            if not self.scraper.navigate_to_book(url):
                self.log_message(self.scraper_log, "Navigation failed")
                return

        self.scraper.force_startnum = self.start_num_var.get()
        # Update current index on scraper
        self.scraper.current_index = self.start_num_var.get()
        self.next_index_var.set(str(self.scraper.current_index))

        self.start_scraping_btn.config(state="disabled")
        self.stop_scraping_btn.config(state="normal")
        self.scraper_progress.start(10)

        def scrape_callback(new_images):
            for url, index in new_images:
                self.log_message(self.scraper_log, f"Downloaded: {index}.png")
                # Update next index display
                self.root.after(0, lambda: self.next_index_var.set(str(self.scraper.current_index)))

        thread = threading.Thread(target=self.scraper.start_scraping, args=(scrape_callback,))
        thread.daemon = True
        thread.start()

        self.log_message(self.scraper_log, "Scraping started...")

    def stop_scraping(self):
        """Stop scraping"""
        if self.scraper:
            self.scraper.stop_scraping()
            self.scraper_progress.stop()
            self.start_scraping_btn.config(state="normal")
            self.stop_scraping_btn.config(state="disabled")

            # Update the start number to the next index for easy resumption
            if hasattr(self.scraper, 'current_index'):
                self.start_num_var.set(self.scraper.current_index)
                self.log_message(self.scraper_log, f"Scraping stopped. Next index: {self.scraper.current_index}")
            else:
                self.log_message(self.scraper_log, "Scraping stopped")

    def close_driver(self):
        """Close Chrome driver"""
        if self.scraper:
            self.scraper.close()
            self.scraper = None
            self.init_driver_btn.config(state="normal")
            self.navigate_btn.config(state="disabled")
            self.start_scraping_btn.config(state="disabled")
            self.stop_scraping_btn.config(state="disabled")
            self.log_message(self.scraper_log, "Driver closed")

    # Zoom methods
    def zoom_in(self):
        """Zoom in the browser"""
        if self.scraper and self.scraper.zoom_in():
            self.update_zoom_status()
            self.log_message(self.scraper_log, "Zoomed in")
        else:
            self.log_message(self.scraper_log, "Failed to zoom in")

    def zoom_out(self):
        """Zoom out the browser"""
        if self.scraper and self.scraper.zoom_out():
            self.update_zoom_status()
            self.log_message(self.scraper_log, "Zoomed out")
        else:
            self.log_message(self.scraper_log, "Failed to zoom out")

    def reset_zoom(self):
        """Reset browser zoom to 100%"""
        if self.scraper and self.scraper.reset_zoom():
            self.zoom_level_var.set(100)
            self.zoom_status_var.set("Zoom: 100%")
            self.log_message(self.scraper_log, "Zoom reset to 100%")
        else:
            self.log_message(self.scraper_log, "Failed to reset zoom")

    def apply_zoom(self):
        """Apply custom zoom level"""
        zoom_level = self.zoom_level_var.get()
        if self.scraper and self.scraper.set_zoom(zoom_level):
            self.zoom_status_var.set(f"Zoom: {zoom_level}%")
            self.log_message(self.scraper_log, f"Zoom set to {zoom_level}%")
        else:
            self.log_message(self.scraper_log, "Failed to set zoom level")

    def update_zoom_status(self):
        """Update zoom status display"""
        if self.scraper and self.scraper.driver:
            try:
                current = self.scraper.driver.execute_script("return document.body.style.zoom || '100%'")
                current_value = int(current.replace('%', ''))
                self.zoom_level_var.set(current_value)
                self.zoom_status_var.set(f"Zoom: {current_value}%")
            except:
                pass

    # Profile management methods
    def check_profile_status(self):
        """Check if Chrome profile exists"""
        profile_dir = os.path.join(os.getcwd(), 'chrome_profile')
        if os.path.exists(profile_dir) and os.listdir(profile_dir):
            self.profile_status_var.set("✓ Profile exists")
            return True
        else:
            self.profile_status_var.set("")
            return False

    def on_profile_toggle(self):
        """Handle profile checkbox toggle"""
        use_profile = self.use_profile_var.get()
        self.settings.set('Scraper', 'use_profile', str(use_profile))
        if use_profile:
            self.log_message(self.scraper_log, "Profile will be used for next driver initialization")
        else:
            self.log_message(self.scraper_log, "Profile will NOT be used for next driver initialization")

    def clear_profile(self):
        """Clear Chrome profile data"""
        if messagebox.askyesno("Clear Profile", "This will delete all saved login sessions and cookies. Are you sure?"):
            profile_dir = os.path.join(os.getcwd(), 'chrome_profile')
            if os.path.exists(profile_dir):
                try:
                    # Close driver if it's running
                    if self.scraper:
                        self.close_driver()

                    # Remove profile directory
                    import shutil
                    shutil.rmtree(profile_dir)
                    self.log_message(self.scraper_log, "Chrome profile cleared successfully")
                    self.profile_status_var.set("")
                    messagebox.showinfo("Success", "Chrome profile has been cleared")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to clear profile: {str(e)}")
                    self.log_message(self.scraper_log, f"Error clearing profile: {e}")
            else:
                messagebox.showinfo("Info", "No profile exists to clear")

    # Converter methods
    def convert_to_png(self):
        """Convert images to PNG"""
        directory = self.convert_dir_var.get()
        if not os.path.exists(directory):
            messagebox.showerror("Error", "Directory does not exist")
            return

        self.converter_progress['value'] = 0
        self.converter_log.delete(1.0, tk.END)

        def callback(message, current=None, total=None):
            self.log_message(self.converter_log, message)
            if current and total:
                progress = (current / total) * 100
                self.converter_progress['value'] = progress
                self.root.update_idletasks()

        def run_conversion():
            file_count, converted, misnamed = self.converter.convert_to_png(directory, callback)
            self.log_message(self.converter_log, f"\nConversion complete: {converted}/{file_count} files")
            if misnamed:
                self.log_message(self.converter_log, f"Fixed {len(misnamed)} misnamed files")

        thread = threading.Thread(target=run_conversion)
        thread.daemon = True
        thread.start()

    def convert_to_jpeg(self):
        """Convert PNG to JPEG"""
        source = self.convert_dir_var.get()
        output = self.jpeg_output_var.get()

        if not os.path.exists(source):
            messagebox.showerror("Error", "Source directory does not exist")
            return

        if not output:
            messagebox.showerror("Error", "Please specify output directory")
            return

        self.converter_progress['value'] = 0

        def callback(message, current=None, total=None):
            self.log_message(self.converter_log, message)
            if current and total:
                progress = (current / total) * 100
                self.converter_progress['value'] = progress
                self.root.update_idletasks()

        def run_conversion():
            processed = self.converter.convert_png_to_jpeg(
                source, output,
                self.apply_sharpness_var.get(),
                callback
            )
            self.log_message(self.converter_log, f"\nConverted {processed} files to JPEG")

        thread = threading.Thread(target=run_conversion)
        thread.daemon = True
        thread.start()

    # Reorder methods
    def preview_files(self):
        """Preview files in directory"""
        directory = self.reorder_dir_var.get()
        if not os.path.exists(directory):
            messagebox.showerror("Error", "Directory does not exist")
            return

        extension = self.reorder_ext_var.get()
        files = self.reorder.get_file_list(directory, extension)

        self.file_listbox.delete(0, tk.END)
        for i, file in enumerate(files):
            new_name = f"{self.reorder_start_var.get() + i}{extension}"
            self.file_listbox.insert(tk.END, f"{file} -> {new_name}")

    def rename_files(self):
        """Rename files"""
        directory = self.reorder_dir_var.get()
        if not os.path.exists(directory):
            messagebox.showerror("Error", "Directory does not exist")
            return

        if not messagebox.askyesno("Confirm", "Are you sure you want to rename all files?"):
            return

        self.reorder_progress['value'] = 0

        def callback(message, current=None, total=None):
            self.file_listbox.insert(tk.END, message)
            self.file_listbox.see(tk.END)
            if current and total:
                progress = (current / total) * 100
                self.reorder_progress['value'] = progress
                self.root.update_idletasks()

        def run_rename():
            self.file_listbox.delete(0, tk.END)
            count = self.reorder.rename_files(
                directory,
                self.reorder_ext_var.get(),
                self.reorder_start_var.get(),
                callback
            )
            messagebox.showinfo("Complete", f"Renamed {count} files")

        thread = threading.Thread(target=run_rename)
        thread.daemon = True
        thread.start()

    # PDF methods
    def create_pdf(self):
        """Create PDF from images"""
        source = self.pdf_source_var.get()
        output = self.pdf_output_var.get()

        if not os.path.exists(source):
            messagebox.showerror("Error", "Source directory does not exist")
            return

        if not output:
            messagebox.showerror("Error", "Please specify output file")
            return

        self.pdf_progress['value'] = 0
        self.pdf_log.delete(1.0, tk.END)

        def callback(message, current=None, total=None):
            self.log_message(self.pdf_log, message)
            if current and total:
                progress = (current / total) * 100
                self.pdf_progress['value'] = progress
                self.root.update_idletasks()

        def run_create():
            success = self.converter.convert_to_pdf(
                source, output,
                self.enhance_color_var.get(),
                self.color_factor_var.get(),
                callback
            )
            if success:
                messagebox.showinfo("Complete", f"PDF created: {output}")
            else:
                messagebox.showerror("Error", "Failed to create PDF")

        thread = threading.Thread(target=run_create)
        thread.daemon = True
        thread.start()

    # Settings tab methods
    def apply_gui_settings(self):
        """Apply current GUI settings to window"""
        width = self.gui_width_var.get()
        height = self.gui_height_var.get()
        x = self.gui_x_var.get()
        y = self.gui_y_var.get()
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.log_message(self.scraper_log, f"GUI window updated: {width}x{height} at ({x}, {y})")

    def preset_side_by_side(self):
        """Set side-by-side preset for windows"""
        # GUI on left
        self.gui_x_var.set(50)
        self.gui_y_var.set(100)
        self.gui_width_var.set(700)
        self.gui_height_var.set(700)
        self.gui_after_x_var.set(50)
        self.gui_after_y_var.set(100)

        # Browser on right
        self.browser_x_var.set(760)
        self.browser_y_var.set(100)
        self.browser_width_var.set(1100)
        self.browser_height_var.set(700)

        messagebox.showinfo("Preset Applied", "Side by Side layout applied")

    def preset_top_bottom(self):
        """Set top-bottom preset for windows"""
        # Browser on top
        self.browser_x_var.set(100)
        self.browser_y_var.set(50)
        self.browser_width_var.set(1400)
        self.browser_height_var.set(500)

        # GUI on bottom
        self.gui_x_var.set(100)
        self.gui_y_var.set(100)
        self.gui_width_var.set(900)
        self.gui_height_var.set(600)
        self.gui_after_x_var.set(100)
        self.gui_after_y_var.set(560)

        messagebox.showinfo("Preset Applied", "Top and Bottom layout applied")

    def preset_default(self):
        """Reset to default window settings"""
        # GUI defaults
        self.gui_x_var.set(100)
        self.gui_y_var.set(100)
        self.gui_width_var.set(900)
        self.gui_height_var.set(700)
        self.gui_after_x_var.set(50)
        self.gui_after_y_var.set(50)

        # Browser defaults
        self.browser_x_var.set(500)
        self.browser_y_var.set(100)
        self.browser_width_var.set(1200)
        self.browser_height_var.set(800)

        messagebox.showinfo("Preset Applied", "Default layout applied")

    def get_current_positions(self):
        """Get current window positions and sizes"""
        # Get GUI window position
        self.root.update_idletasks()
        gui_x = self.root.winfo_x()
        gui_y = self.root.winfo_y()
        gui_width = self.root.winfo_width()
        gui_height = self.root.winfo_height()

        self.gui_x_var.set(gui_x)
        self.gui_y_var.set(gui_y)
        self.gui_width_var.set(gui_width)
        self.gui_height_var.set(gui_height)

        # Get browser position if available
        if self.scraper and self.scraper.driver:
            try:
                position = self.scraper.driver.get_window_position()
                size = self.scraper.driver.get_window_size()

                self.browser_x_var.set(position['x'])
                self.browser_y_var.set(position['y'])
                self.browser_width_var.set(size['width'])
                self.browser_height_var.set(size['height'])

                messagebox.showinfo("Positions Updated",
                    f"Current positions captured:\n"
                    f"GUI: {gui_width}x{gui_height} at ({gui_x}, {gui_y})\n"
                    f"Browser: {size['width']}x{size['height']} at ({position['x']}, {position['y']})")
            except:
                messagebox.showinfo("Positions Updated",
                    f"GUI position captured: {gui_width}x{gui_height} at ({gui_x}, {gui_y})\n"
                    f"Browser not available")
        else:
            messagebox.showinfo("Positions Updated",
                f"GUI position captured: {gui_width}x{gui_height} at ({gui_x}, {gui_y})\n"
                f"Browser not initialized")

    def start_position_tracking(self):
        """Start tracking window positions when Settings tab is active"""
        # Check if Settings tab is active
        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 4:  # Settings tab is index 4
            self.is_tracking = True
            self.update_position_display()
        else:
            self.is_tracking = False

        # Schedule next check
        self.root.after(100, self.start_position_tracking)

    def update_position_display(self):
        """Update the position display labels"""
        if not self.is_tracking:
            return

        try:
            # Check if labels exist (they're created when Settings tab is first opened)
            if hasattr(self, 'gui_current_label'):
                # Update GUI position
                gui_x = self.root.winfo_x()
                gui_y = self.root.winfo_y()
                gui_width = self.root.winfo_width()
                gui_height = self.root.winfo_height()
                self.gui_current_label.config(
                    text=f"GUI Window: Position ({gui_x}, {gui_y}) Size: {gui_width}x{gui_height}"
                )

                # Update Browser position if available
                if self.scraper and self.scraper.driver:
                    try:
                        position = self.scraper.driver.get_window_position()
                        size = self.scraper.driver.get_window_size()
                        self.browser_current_label.config(
                            text=f"Browser: Position ({position['x']}, {position['y']}) Size: {size['width']}x{size['height']}"
                        )
                    except:
                        self.browser_current_label.config(text="Browser: Unable to get position")
                else:
                    self.browser_current_label.config(text="Browser: Not initialized")

        except Exception as e:
            print(f"Error updating position display: {e}")

    def apply_current_gui_position(self):
        """Apply current GUI position to settings"""
        try:
            gui_x = self.root.winfo_x()
            gui_y = self.root.winfo_y()
            gui_width = self.root.winfo_width()
            gui_height = self.root.winfo_height()

            # Update the setting variables
            self.gui_x_var.set(gui_x)
            self.gui_y_var.set(gui_y)
            self.gui_width_var.set(gui_width)
            self.gui_height_var.set(gui_height)

            # Also set as "after browser" position if user wants
            result = messagebox.askyesno("Apply Position",
                f"GUI position applied:\n"
                f"Position: ({gui_x}, {gui_y})\n"
                f"Size: {gui_width}x{gui_height}\n\n"
                f"Also set this as 'After Browser Opens' position?")

            if result:
                self.gui_after_x_var.set(gui_x)
                self.gui_after_y_var.set(gui_y)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply GUI position: {e}")

    def apply_current_browser_position(self):
        """Apply current browser position to settings"""
        if not self.scraper or not self.scraper.driver:
            messagebox.showwarning("No Browser", "Browser is not initialized")
            return

        try:
            position = self.scraper.driver.get_window_position()
            size = self.scraper.driver.get_window_size()

            # Update the setting variables
            self.browser_x_var.set(position['x'])
            self.browser_y_var.set(position['y'])
            self.browser_width_var.set(size['width'])
            self.browser_height_var.set(size['height'])

            messagebox.showinfo("Position Applied",
                f"Browser position applied:\n"
                f"Position: ({position['x']}, {position['y']})\n"
                f"Size: {size['width']}x{size['height']}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply browser position: {e}")

    # Browse methods
    def browse_download_path(self):
        path = filedialog.askdirectory()
        if path:
            self.download_path_var.set(path)

    def browse_convert_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.convert_dir_var.set(path)

    def browse_jpeg_output(self):
        path = filedialog.askdirectory()
        if path:
            self.jpeg_output_var.set(path)

    def browse_reorder_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.reorder_dir_var.set(path)

    def browse_pdf_source(self):
        path = filedialog.askdirectory()
        if path:
            self.pdf_source_var.set(path)

    def browse_pdf_output(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if path:
            self.pdf_output_var.set(path)

    # Utility methods
    def log_message(self, text_widget, message):
        """Log message to text widget"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        text_widget.insert(tk.END, f"[{timestamp}] {message}\n")
        text_widget.see(tk.END)
        self.root.update_idletasks()

    def on_closing(self):
        """Cleanup when GUI is closed"""
        # Check if Chrome driver is still open
        if self.scraper and self.scraper.driver:
            result = messagebox.askyesnocancel(
                "Chrome Driver Active",
                "Chrome browser is still open.\n\n"
                "Yes: Close browser and exit\n"
                "No: Keep browser open and exit\n"
                "Cancel: Don't exit"
            )

            if result is None:  # Cancel
                return
            elif result:  # Yes - close browser
                try:
                    print("Closing Chrome driver...")
                    self.scraper.close()
                    print("Chrome driver closed successfully")
                except Exception as e:
                    print(f"Error closing Chrome driver: {e}")
            # If No, just proceed to destroy GUI without closing browser

        # Destroy the GUI window
        print("Closing GUI...")
        self.root.destroy()


def main():
    root = tk.Tk()
    app = GoogleBooksCrawlerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()