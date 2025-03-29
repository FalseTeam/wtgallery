import os

from PIL import Image, ImageFile, UnidentifiedImageError
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QWidget, QGridLayout, QLabel, QFrame, QSizePolicy, QVBoxLayout

from config import PROJECT_DIR
from utils.logged import Logged
from .components import ClickableImageLabel

# If you need to allow truncated images:
ImageFile.LOAD_TRUNCATED_IMAGES = True


class GalleryWidget(QWidget, Logged):
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        Logged.__init__(self)

        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)
        self.items = []
        self.max_items = 4

        # Initialize no_photo property
        self.__no_photo = None

    @property
    def no_photo(self):
        if self.__no_photo is None:
            self.__no_photo = self.process_single_image(PROJECT_DIR / 'assets' / 'no_photo.jpg')
        return self.__no_photo

    @staticmethod
    def __process_single_image(image_path):
        with Image.open(image_path) as img:
            img.thumbnail((200, 200))
            img = img.convert("RGBA")
            rgba_bytes = img.tobytes("raw", "RGBA")
            return rgba_bytes, img.width, img.height

    def process_single_image(self, image_path):
        """
        Called in a background thread. Loads the image, thumbnails it, and returns
        raw RGBA bytes + the final width/height. We do NOT construct QImage here
        to avoid cross-thread Qt issues.
        """
        try:
            return self.__process_single_image(image_path)
        except UnidentifiedImageError as e:
            self.info(str(e))
            return self.no_photo
        except Exception as e:
            self.warning(str(e), exc_info=e)
            return self.no_photo

    def create_gallery(self, sorted_images, thumbs):
        """
        Runs in the main thread. Clear the old layout, then build new cells
        using the precomputed image thumbnails (already loaded in memory).
        """
        items = []

        for (image_path, similarity_score), (rgba_bytes, w, h) in zip(sorted_images, thumbs):
            cell_frame = QFrame()
            cell_frame.setLayout(QVBoxLayout())
            cell_frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            cell_frame.setFixedWidth(200)

            # Convert the RGBA bytes to a QImage, then QPixmap (main thread only)
            qimage = QImage(rgba_bytes, w, h, QImage.Format.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimage)

            # Use our custom ClickableImageLabel instead of QLabel
            image_label = ClickableImageLabel(image_path, self.parent())
            image_label.setPixmap(pixmap)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_frame.layout().addWidget(image_label)

            # Add file name
            basename = os.path.splitext(os.path.basename(image_path))[0]
            label_name = QLabel(basename)
            label_name.setWordWrap(True)
            cell_frame.layout().addWidget(label_name)

            # Add similarity score
            label_score = QLabel(f"Similarity Score: {similarity_score:.4f}")
            cell_frame.layout().addWidget(label_score)

            items.append(cell_frame)

        self.items = items

        # Decide how many columns based on width:
        # a simple approach: each cell ~220px wide. Always at least 1 col
        num_columns = max(1, self.width() // 220)
        self.max_items = num_columns

        # Remove old widgets from the layout
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, item in enumerate(items):
            row = i // num_columns
            col = i % num_columns
            self.layout.addWidget(item, row, col)

    def resize_gallery(self):
        # Decide how many columns based on width:
        # a simple approach: each cell ~220px wide. Always at least 1 col
        num_columns = max(1, self.width() // 220)

        if self.max_items == num_columns:
            return

        self.max_items = num_columns

        self.layout.children().clear()

        for i, item in enumerate(self.items):
            row = i // num_columns
            col = i % num_columns
            self.layout.addWidget(item, row, col)
