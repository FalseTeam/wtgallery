import asyncio
import os
import subprocess
import sys
from concurrent.futures.thread import ThreadPoolExecutor

import qasync
from PIL import Image, ImageFile
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QScrollArea,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QSizePolicy,
)

from config import EMBEDDINGS_DIR
from indexer import Indexer

# If you need to allow truncated images:
ImageFile.LOAD_TRUNCATED_IMAGES = True


class ImageViewer(QMainWindow):
    def __init__(self):
        super().__init__()

        self.executor = ThreadPoolExecutor()

        self.indexer = Indexer()

        # Preload any/all .pt embeddings on startup
        self.loaded_image_embeddings = {}
        for file in EMBEDDINGS_DIR.glob("*.pt"):
            embeddings = self.indexer.load_image_embeddings(str(file))
            self.loaded_image_embeddings.update(embeddings)

        # UI setup
        self.setWindowTitle("Async Image Gallery (Qt)")
        self.setGeometry(100, 100, 1600, 800)

        self.max_items = 4

        # Main container widget + vertical layout
        main_widget = QWidget()
        main_vlayout = QVBoxLayout(main_widget)
        self.setCentralWidget(main_widget)

        #
        # Row 1: Query controls
        #
        query_layout = QHBoxLayout()
        # Query label
        label_query = QLabel("Query:")
        query_layout.addWidget(label_query)
        # Query entry
        self.query_entry = QLineEdit()
        self.query_entry.returnPressed.connect(
            lambda: asyncio.create_task(self.search_and_update_gallery())
        )
        query_layout.addWidget(self.query_entry)

        # Top K label
        label_topk = QLabel("Top K:")
        query_layout.addWidget(label_topk)
        # ComboBox for top_k
        self.top_k_combobox = QComboBox()
        self.top_k_combobox.addItems([str(x) for x in [21, 28, 35, 42, 49, 56, 63, 70, 77, 84, 91, 98]])
        self.top_k_combobox.setCurrentText("49")
        query_layout.addWidget(self.top_k_combobox)

        # Search button
        search_button = QPushButton("Search")
        search_button.clicked.connect(
            lambda: asyncio.create_task(self.search_and_update_gallery())
        )
        query_layout.addWidget(search_button)

        main_vlayout.addLayout(query_layout)

        #
        # Row 2: Scroll area for images
        #
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        # self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_vlayout.addWidget(self.scroll_area)

        self.gallery_widget = QWidget()
        self.gallery_layout = QGridLayout(self.gallery_widget)
        self.gallery_layout.setContentsMargins(10, 10, 10, 10)
        self.gallery_layout.setSpacing(10)
        self.scroll_area.setWidget(self.gallery_widget)
        self.items = []

        #
        # "Loading" overlay (hidden by default)
        #
        self.loading_overlay = QLabel(self)
        self.loading_overlay.setText("Loading…")
        self.loading_overlay.setStyleSheet(
            "QLabel { background-color: rgba(0,0,0,0.4); color: white; font-size: 24px; }"
        )
        self.loading_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_overlay.setVisible(False)
        self.loading_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # Manually ensure it covers the entire window:
        self.resizeEvent(QResizeEvent(self.size(), self.size()))

    def resizeEvent(self, event):
        """
        Overridden to always resize the overlay to cover the entire window.
        """
        super().resizeEvent(event)
        if self.loading_overlay is not None:
            self.loading_overlay.setGeometry(self.rect())
        self.resize_gallery(event)

    def show_overlay(self):
        self.loading_overlay.setVisible(True)

    def hide_overlay(self):
        self.loading_overlay.setVisible(False)

    @staticmethod
    def open_image_in_viewer(image_path: str) -> None:
        """Cross-platform attempt to open image in default viewer."""
        try:
            if os.name == "nt":
                subprocess.run(["explorer", image_path], check=True)
            elif os.name == "posix":
                subprocess.run(["xdg-open", image_path], check=True)
            else:
                print("Unsupported OS. Unable to open the image in the default viewer.")
        except subprocess.CalledProcessError as e:
            print(f"Error opening image '{image_path}' in the default image viewer: {e}")

    async def search_and_update_gallery(self):
        """
        Perform the embedding-based search in a background thread,
        then generate all thumbnails in another background thread,
        then update the UI in the main thread.
        """
        self.show_overlay()
        # Let the overlay actually repaint:
        await asyncio.sleep(0)

        query = self.query_entry.text().strip()
        top_k = int(self.top_k_combobox.currentText())

        #
        # 1) Run your search in a background thread
        #
        loop = asyncio.get_event_loop()
        # Using partial if your indexer method has signature like `search(query, embeddings_dict)`.
        # Adjust to however you actually do your sorting.
        sorted_images = await loop.run_in_executor(
            self.executor,
            self.indexer.search_images_by_text, self.loaded_image_embeddings, query
        )

        # Just for safety: limit top_k
        sorted_images = sorted_images[:top_k]

        #
        # 2) Load and thumbnail images in background
        #
        image_paths = [x[0] for x in sorted_images]  # each x is (image_path, similarity_score)
        thumbs = await self.generate_thumbnails(image_paths)

        #
        # 3) Update the gallery in the main thread
        #
        self.create_gallery(sorted_images, thumbs)
        self.scroll_area.verticalScrollBar().setValue(0)

        self.hide_overlay()

    async def generate_thumbnails(self, image_paths):
        """
        Offload the expensive PIL I/O and .thumbnail(...) to a background thread.
        We return a list of (raw_rgba_bytes, width, height).
        """
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(self.executor, self.process_single_image, path)
            for path in image_paths
        ]
        results = await asyncio.gather(*tasks)
        return results

    @staticmethod
    def process_single_image(image_path):
        """
        Called in a background thread. Loads the image, thumbnails it, and returns
        raw RGBA bytes + the final width/height. We do NOT construct QImage here
        to avoid cross-thread Qt issues.
        """
        with Image.open(image_path) as img:
            img.thumbnail((200, 200))
            img = img.convert("RGBA")
            rgba_bytes = img.tobytes("raw", "RGBA")
            return rgba_bytes, img.width, img.height

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

            image_label = QLabel()
            image_label.setPixmap(pixmap)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image_label.mousePressEvent = (
                lambda event, p=image_path: self.on_image_click(event, p)
            )
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
        num_columns = max(1, self.gallery_widget.width() // 220)
        self.max_items = num_columns

        # Remove old widgets from the layout
        while self.gallery_layout.count():
            item = self.gallery_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, item in enumerate(items):
            row = i // num_columns
            col = i % num_columns
            self.gallery_layout.addWidget(item, row, col)

    def resize_gallery(self, _: QResizeEvent = None):
        # Decide how many columns based on width:
        # a simple approach: each cell ~220px wide. Always at least 1 col
        num_columns = max(1, self.gallery_widget.width() // 220)

        if self.max_items == num_columns:
            return

        self.max_items = num_columns

        self.gallery_layout.children().clear()

        for i, item in enumerate(self.items):
            row = i // num_columns
            col = i % num_columns
            self.gallery_layout.addWidget(item, row, col)


    def on_image_click(self, _, image_path):
        """Called when the user clicks on an image label."""
        self.open_image_in_viewer(image_path)


async def main_async():
    """
    Main coroutine. We create the QApplication + ImageViewer, show it,
    and let the event loop run via qasync.
    """
    viewer = ImageViewer()
    viewer.show()
    # Optionally do an initial empty search or something here:
    await asyncio.sleep(0)
    await viewer.search_and_update_gallery()


def main():
    """
    Standard if __name__ == '__main__': approach to run the app with qasync.
    """
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(main_async())
        loop.run_forever()
    finally:
        loop.close()


if __name__ == "__main__":
    main()
