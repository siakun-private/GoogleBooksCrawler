"""
Settings manager for saving and loading user preferences
"""

import configparser
import os


class SettingsManager:
    def __init__(self, settings_file="settings.ini"):
        self.settings_file = settings_file
        self.config = configparser.ConfigParser()
        self.load_settings()

    def load_settings(self):
        """Load settings from INI file"""
        if os.path.exists(self.settings_file):
            self.config.read(self.settings_file)
        else:
            # Create default settings
            self.create_default_settings()

    def create_default_settings(self):
        """Create default settings structure"""
        # Scraper settings
        self.config['Scraper'] = {
            'book_url': 'https://play.google.com/books/reader?id=',
            'download_path': os.path.join(os.getcwd(), 'Downloads'),
            'force_start_number': '0',
            'use_profile': 'True',
            'zoom_level': '100'
        }

        # Converter settings
        self.config['Converter'] = {
            'directory': os.path.join(os.getcwd(), 'Downloads'),
            'jpeg_output': '',
            'apply_sharpness': 'True'
        }

        # Reorder settings
        self.config['Reorder'] = {
            'directory': os.path.join(os.getcwd(), 'Downloads'),
            'file_extension': '.png',
            'start_number': '0'
        }

        # PDF settings
        self.config['PDF'] = {
            'source_directory': os.path.join(os.getcwd(), 'Downloads'),
            'output_file': os.path.join(os.getcwd(), 'output.pdf'),
            'enhance_color': 'True',
            'color_factor': '1.5'
        }

        # Window settings
        self.config['Window'] = {
            'gui_width': '900',
            'gui_height': '700',
            'gui_x': '100',
            'gui_y': '100',
            'gui_after_browser_x': '50',
            'gui_after_browser_y': '50',
            'browser_width': '1200',
            'browser_height': '800',
            'browser_x': '500',
            'browser_y': '100'
        }

        self.save_settings()

    def save_settings(self):
        """Save settings to INI file"""
        with open(self.settings_file, 'w') as configfile:
            self.config.write(configfile)

    def get(self, section, key, default=None):
        """Get a setting value"""
        try:
            return self.config.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    def set(self, section, key, value):
        """Set a setting value"""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))
        self.save_settings()

    def get_bool(self, section, key, default=False):
        """Get a boolean setting value"""
        try:
            return self.config.getboolean(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    def get_int(self, section, key, default=0):
        """Get an integer setting value"""
        try:
            return self.config.getint(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default

    def get_float(self, section, key, default=0.0):
        """Get a float setting value"""
        try:
            return self.config.getfloat(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default