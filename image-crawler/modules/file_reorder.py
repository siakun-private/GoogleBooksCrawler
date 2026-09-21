"""
File reordering module for renaming files in natural numeric order
"""

import os
import re


class FileReorder:
    @staticmethod
    def natural_keys(text):
        """Extract numbers from filename for natural sorting"""
        parts = re.split(r'(\d+\.\d+|\d+)', text)
        keys = []
        for part in parts:
            if part.isdigit():
                keys.append(int(part))
            elif re.match(r'\d+\.\d+', part):
                keys.append(float(part))
            else:
                keys.append(part)
        return keys

    def rename_files(self, directory, extension='.png', start_number=0, callback=None):
        """Rename files in natural numeric order"""
        # Get all files with specified extension
        files = [f for f in os.listdir(directory) if f.endswith(extension)]
        total_files = len(files)

        if callback:
            callback(f"Found {total_files} {extension} files")

        # Sort files in natural order
        files.sort(key=self.natural_keys)

        # First pass: rename to temporary names to avoid conflicts
        temp_files = []
        for i, original in enumerate(files):
            temp_name = f"temp_{i}{extension}"
            temp_files.append(temp_name)
            try:
                os.rename(
                    os.path.join(directory, original),
                    os.path.join(directory, temp_name)
                )
                if callback:
                    callback(f"Temp rename: {original} -> {temp_name}", i + 1, total_files * 2)
            except Exception as e:
                print(f"Error renaming {original}: {e}")

        # Second pass: rename to final names
        for i, temp in enumerate(temp_files):
            final_name = f"{start_number + i}{extension}"
            try:
                os.rename(
                    os.path.join(directory, temp),
                    os.path.join(directory, final_name)
                )
                if callback:
                    callback(f"Final rename: {temp} -> {final_name}", total_files + i + 1, total_files * 2)
            except Exception as e:
                print(f"Error renaming {temp}: {e}")

        if callback:
            callback(f"Renamed {total_files} files successfully")

        return total_files

    def get_file_list(self, directory, extension='.png'):
        """Get sorted list of files"""
        files = [f for f in os.listdir(directory) if f.endswith(extension)]
        files.sort(key=self.natural_keys)
        return files