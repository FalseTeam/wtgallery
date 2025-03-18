IMG_EXTENSIONS = (".jpg", ".jpeg", ".png", ".ppm", ".bmp", ".gif", ".pgm", ".tif", ".tiff", ".webp")


def is_image_file(filename: str) -> bool:
    return filename.lower().endswith(IMG_EXTENSIONS)
