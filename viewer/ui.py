import asyncio
import os
import subprocess
import sys
from concurrent.futures.thread import ThreadPoolExecutor

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QHBoxLayout,
    QMenuBar,
    QMessageBox,
    QComboBox,
)

from config import EMBEDDINGS_DIR, PROJECT_DIR
from indexer import Indexer
from utils.lazy import Lazy
from utils.logged import Logged
from .components import ImageQueryLineEdit
from .dialogs import IndexerSettingsDialog
from .gallery import GalleryWidget
from .theme import ThemeManager


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

        # Create menu bar
        self.create_menu_bar()

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

        # Refresh embeddings button
        self.refresh_button = QPushButton("Refresh Embeddings")
        self.refresh_button.clicked.connect(
            lambda: asyncio.create_task(self.reload_embeddings_and_search())
        )
        self.refresh_button.setToolTip("Reload embeddings and refresh search results")
        query_layout.addWidget(self.refresh_button)

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
        main_vlayout.addWidget(self.scroll_area)

        self.gallery_widget = GalleryWidget(self)
        self.scroll_area.setWidget(self.gallery_widget)

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

        self.__no_photo = Lazy(
            lambda: self.gallery_widget.process_single_image(PROJECT_DIR / 'assets' / 'no_photo.jpg'))

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
        self.gallery_widget.resize_gallery()

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
        self.gallery_widget.create_gallery(sorted_images, thumbs)
        self.scroll_area.verticalScrollBar().setValue(0)

        self.hide_overlay()

    async def generate_thumbnails(self, image_paths):
        """
        Offload the expensive PIL I/O and .thumbnail(...) to a background thread.
        We return a list of (raw_rgba_bytes, width, height).
        """
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(self.executor, self.gallery_widget.process_single_image, path)
            for path in image_paths
        ]
        results = await asyncio.gather(*tasks)
        return results

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
        self.gallery_widget.create_gallery(sorted_images, thumbs)
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

    def create_menu_bar(self):
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        # File menu
        file_menu = menu_bar.addMenu("File")

        # Settings menu item
        settings_action = file_menu.addAction("Indexer Settings...")
        settings_action.triggered.connect(self.show_indexer_settings)

        # Exit menu item
        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

    def show_indexer_settings(self):
        """Show the indexer settings dialog"""
        # Create dialog as a child of this window
        dialog = IndexerSettingsDialog(self, self.indexer)

        # Connect a signal to know when to reload embeddings
        dialog.accepted.connect(self.reload_embeddings)
        dialog.finished.connect(self.reload_embeddings)

        # Show the dialog non-modally to allow async operations to continue
        dialog.show()

        # Note: We don't use exec() which would block until dialog is closed
        # This allows async operations within the dialog to continue

    def reload_embeddings(self):
        """Reload all embeddings from disk"""
        # Ensure embeddings directory exists
        if not EMBEDDINGS_DIR.exists():
            self.info(f"Creating embeddings directory: {EMBEDDINGS_DIR}")
            EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

        old_embeddings = self.loaded_image_embeddings
        self.loaded_image_embeddings = {}

        embedding_stats = {}

        # Check if there are any embedding files
        embedding_files = list(EMBEDDINGS_DIR.glob("*.pt"))
        if not embedding_files:
            self.warning(f"No embedding files found in {EMBEDDINGS_DIR}")
            return {}

        # Load each embedding file
        for file in embedding_files:
            try:
                self.info(f"Loading embeddings from {file}")
                embeddings = self.indexer.load_image_embeddings(str(file))

                # Extract source information from filename
                source_info = file.stem  # filename without extension

                # Store stats for reporting
                embedding_stats[source_info] = len(embeddings)

                # Add to combined embeddings
                self.loaded_image_embeddings.update(embeddings)

            except Exception as e:
                self.error(f"Error loading embeddings from {file}: {str(e)}", exc_info=e)

        # Log information about loaded embeddings
        total_embeddings = len(self.loaded_image_embeddings)
        self.info(f"Loaded {total_embeddings} total embeddings from {len(embedding_stats)} files")

        # Log details about each source
        for source, count in embedding_stats.items():
            self.info(f"  - {source}: {count} embeddings")

        return embedding_stats

    async def reload_embeddings_and_search(self):
        """Reload embeddings and update search results"""
        self.show_overlay()
        # Let the overlay actually repaint:
        await asyncio.sleep(0)

        old_count = len(self.loaded_image_embeddings)
        stats = self.reload_embeddings()
        new_count = len(self.loaded_image_embeddings)

        # Update the search if we have a query
        if self.query_entry.text().strip():
            await self.search_and_update_gallery()

        self.hide_overlay()

        # Show a message with detailed stats
        if stats:
            # Create a detailed message with embeddings from each source
            message = f"Embeddings refreshed successfully.\n\nTotal images: {new_count}"

            if new_count != old_count:
                diff = new_count - old_count
                if diff > 0:
                    message += f" (+{diff})"
                else:
                    message += f" ({diff})"

            message += "\n\nDetails:"
            for source, count in stats.items():
                message += f"\n• {source}: {count} images"

            QMessageBox.information(
                self,
                "Embeddings Refreshed",
                message,
                QMessageBox.StandardButton.Ok
            )
        else:
            QMessageBox.information(
                self,
                "No Embeddings Found",
                "No embedding files were found in the embeddings directory.",
                QMessageBox.StandardButton.Ok
            )
