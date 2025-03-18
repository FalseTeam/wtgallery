import asyncio
import os
import subprocess
import sys
import tempfile
from concurrent.futures.thread import ThreadPoolExecutor
from pathlib import Path

import qasync
from PIL import Image, ImageFile, UnidentifiedImageError
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage, QResizeEvent, QCursor
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
    QMenu,
)

from config import EMBEDDINGS_DIR, PROJECT_DIR
from indexer import Indexer
from utils import logcfg
from utils.lazy import Lazy
from utils.logged import Logged

# If you need to allow truncated images:
ImageFile.LOAD_TRUNCATED_IMAGES = True


class ThemeManager:
    def __init__(self):
        self.is_dark = True
        self._dark_theme = """
            QMainWindow, QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
            }
            QLineEdit {
                background-color: #3b3b3b;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 3px;
            }
            QComboBox {
                background-color: #3b3b3b;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 3px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: url(down_arrow_white.png);
            }
            QPushButton {
                background-color: #4b4b4b;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #5b5b5b;
            }
            QScrollArea {
                background-color: #2b2b2b;
                border: 1px solid #555555;
            }
            QFrame {
                background-color: #3b3b3b;
                border: 1px solid #555555;
                border-radius: 3px;
            }
            QMenu {
                background-color: #3b3b3b;
                color: #ffffff;
                border: 1px solid #555555;
            }
            QMenu::item:selected {
                background-color: #4b4b4b;
            }
        """
        self._light_theme = """
            QMainWindow, QWidget {
                background-color: #ffffff;
                color: #000000;
            }
            QLabel {
                color: #000000;
            }
            QLineEdit {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 5px;
                border-radius: 3px;
            }
            QComboBox {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 5px;
                border-radius: 3px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: url(down_arrow_black.png);
            }
            QPushButton {
                background-color: #f0f0f0;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QScrollArea {
                background-color: #ffffff;
                border: 1px solid #cccccc;
            }
            QFrame {
                background-color: #f5f5f5;
                border: 1px solid #cccccc;
                border-radius: 3px;
            }
            QMenu {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
            }
            QMenu::item:selected {
                background-color: #e0e0e0;
            }
        """

    def get_current_theme(self):
        return self._dark_theme if self.is_dark else self._light_theme

    def toggle_theme(self):
        self.is_dark = not self.is_dark
        return self.get_current_theme()


class ImageQueryLineEdit(QLineEdit):
    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self.viewer = viewer
        self.setPlaceholderText("Enter text query or paste an image (Ctrl+V/Cmd+V)")
        self.temp_image_path = None

    def keyPressEvent(self, event):
        # Handle paste event
        if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._handle_paste()
        else:
            super().keyPressEvent(event)

    def _handle_paste(self):
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()

        if mime_data.hasImage():
            # Get image from clipboard
            image = clipboard.image()
            if not image.isNull():
                # Create temporary directory if it doesn't exist
                temp_dir = Path(tempfile.gettempdir()) / "image_viewer_queries"
                temp_dir.mkdir(exist_ok=True)

                # Save previous temporary file if it exists
                if self.temp_image_path and os.path.exists(self.temp_image_path):
                    try:
                        os.remove(self.temp_image_path)
                    except OSError:
                        pass

                # Save new temporary file
                self.temp_image_path = str(temp_dir / f"pasted_query_{id(self)}.png")
                image.save(self.temp_image_path, "PNG")

                # Update UI to show image was pasted
                self.setText("[Pasted Image]")
                self.selectAll()

                # Trigger search with the pasted image
                asyncio.create_task(self.viewer.search_similar_images(self.temp_image_path))

    def cleanup(self):
        """Clean up temporary files when closing"""
        if self.temp_image_path and os.path.exists(self.temp_image_path):
            try:
                os.remove(self.temp_image_path)
            except OSError:
                pass


class ClickableImageLabel(QLabel, Logged):
    def __init__(self, image_path: str, viewer, parent=None):
        QLabel.__init__(self, parent)
        Logged.__init__(self)
        self.image_path = image_path
        self.viewer = viewer
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, position):
        menu = QMenu()
        open_action = menu.addAction("Open in Viewer")
        find_similar_action = menu.addAction("Find Similar Images")
        copy_action = menu.addAction("Copy to Clipboard")

        action = menu.exec(QCursor.pos())
        if not action:
            return

        self.debug(f"{action.text()}: {self.image_path}")
        if action == open_action:
            self.viewer.on_image_click(None, self.image_path)
        elif action == find_similar_action:
            asyncio.create_task(self.viewer.search_similar_images(self.image_path))
        elif action == copy_action:
            # Load and copy image to clipboard
            image = QImage(self.image_path)
            if not image.isNull():
                QApplication.clipboard().setImage(image)


class ImageViewer(QMainWindow, Logged):
    def __init__(self):
        QMainWindow.__init__(self)
        Logged.__init__(self)

        self.executor = ThreadPoolExecutor(thread_name_prefix='Viewer-Background')
        self.theme_manager = ThemeManager()

        self.indexer = Indexer()

        # Preload any/all .pt embeddings on startup
        self.loaded_image_embeddings = {}
        for file in EMBEDDINGS_DIR.glob("*.pt"):
            embeddings = self.indexer.load_image_embeddings(str(file))
            self.loaded_image_embeddings.update(embeddings)

        # UI setup
        self.setWindowTitle("WTGallery")
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

        # Theme toggle button
        self.theme_button = QPushButton("Toggle Theme")
        self.theme_button.clicked.connect(self.toggle_theme)
        query_layout.addWidget(self.theme_button)

        # Query label
        label_query = QLabel("Query:")
        query_layout.addWidget(label_query)

        # Query entry with image paste support
        self.query_entry = ImageQueryLineEdit(self)
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
        self.top_k_combobox.setMinimumWidth(60)  # Set minimum width to fit all numbers
        self.top_k_combobox.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)  # Adjust to content width
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
            "QLabel { background-color: rgba(0,0,0,0.4); "
            f"color: {'white' if self.theme_manager.is_dark else 'black'}; "
            "font-size: 24px; }"
        )
        self.loading_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_overlay.setVisible(False)
        self.loading_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # Manually ensure it covers the entire window:
        self.resizeEvent(QResizeEvent(self.size(), self.size()))

        # Apply initial theme
        self.setStyleSheet(self.theme_manager.get_current_theme())

        self.__no_photo = Lazy(lambda: self.__process_single_image(PROJECT_DIR / 'assets' / 'no_photo.jpg'))

    @property
    def no_photo(self):
        return self.__no_photo.get()

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

    def open_image_in_viewer(self, image_path: str) -> None:
        """Cross-platform attempt to open image in default viewer."""
        try:
            if os.name == "nt":  # Windows
                os.startfile(image_path)
            elif sys.platform == "darwin":  # macOS
                subprocess.run(["open", image_path], check=True)
            elif os.name == "posix":  # Linux and other Unix-like
                subprocess.run(["xdg-open", image_path], check=True)
            else:
                self.warning(f"Unsupported OS {os.name} platform {sys.platform}. Unable to open the image outside.")
        except (subprocess.CalledProcessError, OSError) as e:
            self.warning(f"Error opening image '{image_path}' in the default image viewer: {e}", exc_info=True)

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
            image_label = ClickableImageLabel(image_path, self)
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

    async def search_similar_images(self, query_image_path: str):
        """Search for images similar to the selected image."""
        self.show_overlay()
        # Let the overlay actually repaint:
        await asyncio.sleep(0)

        top_k = int(self.top_k_combobox.currentText())

        #
        # 1) Run your search in a background thread
        #
        loop = asyncio.get_event_loop()
        sorted_images = await loop.run_in_executor(
            self.executor,
            self.indexer.search_images_by_image, self.loaded_image_embeddings, query_image_path
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

    def on_image_click(self, _, image_path):
        """Called when the user clicks on an image label."""
        self.open_image_in_viewer(image_path)

    def toggle_theme(self):
        """Toggle between light and dark themes"""
        new_theme = self.theme_manager.toggle_theme()
        self.setStyleSheet(new_theme)
        # Update loading overlay style
        self.loading_overlay.setStyleSheet(
            "QLabel { background-color: rgba(0,0,0,0.4); "
            f"color: {'white' if self.theme_manager.is_dark else 'black'}; "
            "font-size: 24px; }"
        )


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
    logcfg.apply()
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
