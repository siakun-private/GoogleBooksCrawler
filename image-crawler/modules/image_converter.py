"""
Image conversion module for processing downloaded images
"""

import os
import re
from PIL import Image, ImageFile, ImageEnhance, ImageFilter


class ImageConverter:
    def __init__(self):
        # Enable loading of truncated images
        ImageFile.LOAD_TRUNCATED_IMAGES = True

    def natural_sort_key(self, filename):
        """Convert a filename to a list of mixed numbers and strings for natural sorting"""
        def tryint(s):
            try:
                return int(s)
            except ValueError:
                return s

        return [tryint(c) for c in re.split('([0-9]+)', filename)]

    def convert_to_png(self, directory_path, callback=None):
        """Convert all images in directory to PNG format"""
        file_count = 0
        misnamed_files = []
        converted_count = 0

        # First pass: count files and detect misnamed files
        for filename in os.listdir(directory_path):
            file_path = os.path.join(directory_path, filename)
            if os.path.isfile(file_path) and file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                file_count += 1
                try:
                    with Image.open(file_path) as img:
                        if img.format != 'PNG' and file_path.lower().endswith('.png'):
                            misnamed_files.append(filename)
                except Exception as e:
                    print(f"Error checking {filename}: {e}")

        if callback:
            callback(f"Found {file_count} image files")

        # Second pass: convert to PNG
        for filename in os.listdir(directory_path):
            file_path = os.path.join(directory_path, filename)
            if os.path.isfile(file_path) and file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                try:
                    with Image.open(file_path) as img:
                        new_file_path = os.path.join(directory_path, os.path.splitext(filename)[0] + '.png')
                        img.save(new_file_path, 'PNG')
                        converted_count += 1

                        if filename in misnamed_files and callback:
                            callback(f"Fixed misnamed file: {filename}")

                        if callback:
                            callback(f"Converted: {filename}", converted_count, file_count)

                except Exception as e:
                    print(f"Error converting {filename}: {e}")

        return file_count, converted_count, misnamed_files

    def apply_unsharp_mask(self, image):
        """Apply unsharp mask filter to image"""
        enhanced_img = image.filter(ImageFilter.UnsharpMask(radius=3, percent=100, threshold=5))
        return enhanced_img

    def convert_png_to_jpeg(self, source_folder, output_folder, apply_sharpness=True, callback=None):
        """Convert PNG images to JPEG with optional sharpness enhancement"""
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        files = [f for f in os.listdir(source_folder) if f.endswith('.png')]
        total_files = len(files)
        processed = 0

        for file_name in files:
            file_path = os.path.join(source_folder, file_name)
            output_file_name = file_name.replace('.png', '.jpg')
            output_file_path = os.path.join(output_folder, output_file_name)

            try:
                with Image.open(file_path) as img:
                    # Convert to RGB mode (JPEG only supports RGB)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')

                    if apply_sharpness:
                        enhancer = ImageEnhance.Sharpness(img)
                        img = enhancer.enhance(1.2)

                    # Save as JPEG with maximum quality
                    img.save(output_file_path, 'JPEG', quality=100)
                    processed += 1

                    if callback:
                        callback(f"Converted to JPEG: {file_name}", processed, total_files)

            except Exception as e:
                print(f"Error converting {file_name}: {e}")

        return processed

    def enhance_image_color(self, file_path, color_factor=1.5):
        """Enhance color of image"""
        with Image.open(file_path) as img:
            # Convert to RGB mode
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Enhance color
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(color_factor)

            return img

    def convert_to_pdf(self, source_folder, output_filename, enhance_color=True, color_factor=1.5, callback=None):
        """Convert PNG images to single PDF"""
        images = []
        files = sorted([f for f in os.listdir(source_folder) if f.endswith('.png')], key=self.natural_sort_key)
        total_files = len(files)
        processed = 0

        for file_name in files:
            file_path = os.path.join(source_folder, file_name)
            try:
                if enhance_color:
                    image = self.enhance_image_color(file_path, color_factor)
                else:
                    with Image.open(file_path) as img:
                        if img.mode != 'RGB':
                            image = img.convert('RGB')
                        else:
                            image = img.copy()

                images.append(image)
                processed += 1

                if callback:
                    callback(f"Processing: {file_name}", processed, total_files)

            except Exception as e:
                print(f"Error processing {file_name}: {e}")

        if images:
            images[0].save(output_filename, save_all=True, append_images=images[1:])
            if callback:
                callback(f"PDF created: {output_filename}")
            return True
        else:
            if callback:
                callback("No PNG images found to convert")
            return False