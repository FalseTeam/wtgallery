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
    QDialog,
    QFileDialog,
    QListWidget,
    QMenuBar,
    QMessageBox,
    QProgressBar,
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


class IndexerSettingsDialog(QDialog, Logged):
    def __init__(self, parent=None, indexer=None):
        QDialog.__init__(self, parent)
        Logged.__init__(self)
        
        self.indexer = indexer
        self.pending_task = None  # Track the running indexing task
        self.setWindowTitle("Indexer Settings")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        
        # Main layout
        layout = QVBoxLayout(self)
        
        # Current embeddings info
        self.embeddings_info_label = QLabel("Current Embeddings:")
        layout.addWidget(self.embeddings_info_label)
        
        self.embeddings_info = QListWidget()
        self.embeddings_info.setMaximumHeight(150)
        layout.addWidget(self.embeddings_info)
        
        # Load current embeddings info
        self.load_embeddings_info()
        
        # Directories list
        self.directories_label = QLabel("Directories to index:")
        layout.addWidget(self.directories_label)
        
        self.directories_list = QListWidget()
        layout.addWidget(self.directories_list)
        
        # Buttons for directory management
        dir_buttons_layout = QHBoxLayout()
        
        self.add_dir_button = QPushButton("Add Directory")
        self.add_dir_button.clicked.connect(self.add_directory)
        dir_buttons_layout.addWidget(self.add_dir_button)
        
        self.remove_dir_button = QPushButton("Remove Directory")
        self.remove_dir_button.clicked.connect(self.remove_directory)
        dir_buttons_layout.addWidget(self.remove_dir_button)
        
        layout.addLayout(dir_buttons_layout)
        
        # Model selection
        model_layout = QHBoxLayout()
        
        self.model_label = QLabel("CLIP Model:")
        model_layout.addWidget(self.model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.addItem("laion/CLIP-ViT-H-14-laion2B-s32B-b79K", "LaionH14")
        self.model_combo.addItem("openai/clip-vit-large-patch14", "OpenAILargePatch14")
        self.model_combo.addItem("openai/clip-vit-large-patch14-336", "OpenAILargePatch14_336")
        self.model_combo.addItem("openai/clip-vit-base-patch16", "OpenAIBasePatch16")
        
        model_layout.addWidget(self.model_combo)
        
        layout.addLayout(model_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Progress indicator
        self.progress_label = QLabel("Ready")
        layout.addWidget(self.progress_label)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        
        self.index_button = QPushButton("Start Indexing")
        self.index_button.clicked.connect(
            self._start_indexing_clicked
        )
        buttons_layout.addWidget(self.index_button)
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        buttons_layout.addWidget(self.close_button)
        
        layout.addLayout(buttons_layout)
    
    def load_embeddings_info(self):
        """Load and display information about current embeddings"""
        self.embeddings_info.clear()
        
        try:
            # Ensure embeddings directory exists
            if not EMBEDDINGS_DIR.exists():
                self.info(f"Embeddings directory does not exist: {EMBEDDINGS_DIR}")
                self.embeddings_info.addItem("No embeddings directory found. It will be created when indexing.")
                return
                
            # Get all embedding files
            embeddings_files = list(EMBEDDINGS_DIR.glob("*.pt"))
            
            if not embeddings_files:
                self.embeddings_info.addItem("No embeddings found.")
                return
                
            total_images = 0
            source_stats = {}
            
            for file in embeddings_files:
                try:
                    # Load embeddings to get count
                    embeddings = self.indexer.load_image_embeddings(str(file))
                    num_images = len(embeddings)
                    total_images += num_images
                    
                    # Extract info from filename
                    source_info = file.stem  # filename without extension
                    source_stats[source_info] = num_images
                    
                    # Add to list with image count
                    self.embeddings_info.addItem(f"{source_info}: {num_images} images")
                except Exception as e:
                    error_msg = f"{file.name}: Error loading ({str(e)})"
                    self.embeddings_info.addItem(error_msg)
                    self.error(error_msg, exc_info=e)
            
            # Add summary item at the top - prepend to make it first
            # Get the current items
            items = []
            for i in range(self.embeddings_info.count()):
                items.append(self.embeddings_info.item(i).text())
            
            # Clear and re-add with summary first
            self.embeddings_info.clear()
            self.embeddings_info.addItem(f"Total: {total_images} images across {len(embeddings_files)} embedding files")
            
            # Add back the individual entries
            for item in items:
                self.embeddings_info.addItem(item)
            
        except Exception as e:
            error_msg = f"Error loading embeddings info: {str(e)}"
            self.error(error_msg, exc_info=e)
            self.embeddings_info.addItem(error_msg)
    
    def reload_embeddings_info(self):
        """Reload the embeddings info after indexing completes"""
        self.load_embeddings_info()
    
    def add_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Directory to Index", str(Path.home())
        )
        if dir_path:
            self.directories_list.addItem(dir_path)
    
    def remove_directory(self):
        selected_items = self.directories_list.selectedItems()
        for item in selected_items:
            self.directories_list.takeItem(self.directories_list.row(item))
    
    async def start_indexing(self):
        if self.directories_list.count() == 0:
            QMessageBox.warning(self, "No Directories", "Please add at least one directory to index.")
            return
        
        # Get selected model
        model_key = self.model_combo.currentData()
        
        # Disable UI elements during indexing
        self.index_button.setEnabled(False)
        self.add_dir_button.setEnabled(False)
        self.remove_dir_button.setEnabled(False)
        self.model_combo.setEnabled(False)
        self.close_button.setEnabled(False)  # Also disable close button
        
        self.progress_label.setText("Indexing in progress...")
        self.progress_bar.setValue(0)
        
        # Set the model based on selection
        from models import CLIP
        model_map = {
            "LaionH14": CLIP.LaionH14,
            "OpenAILargePatch14": CLIP.OpenAILargePatch14,
            "OpenAILargePatch14_336": CLIP.OpenAILargePatch14_336,
            "OpenAIBasePatch16": CLIP.OpenAIBasePatch16,
        }
        
        selected_model = model_map.get(model_key, CLIP.LaionH14)
        self.info(f"Using CLIP model: {model_key} ({selected_model.name})")
        self.indexer = Indexer(clip_model=selected_model)
        
        # Also log the embeddings directory
        self.info(f"Embeddings will be saved to: {EMBEDDINGS_DIR}")
        
        # Ensure embeddings directory exists
        if not EMBEDDINGS_DIR.exists():
            self.info(f"Creating embeddings directory: {EMBEDDINGS_DIR}")
            EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Process each directory
        loop = asyncio.get_event_loop()
        new_embeddings_created = False
        
        try:
            total_dirs = self.directories_list.count()
            for i in range(total_dirs):
                dir_path = self.directories_list.item(i).text()
                self.progress_label.setText(f"Indexing: {dir_path}")
                self.progress_bar.setValue(int((i / total_dirs) * 100))
                
                # Check if the directory exists
                if not Path(dir_path).exists():
                    self.warning(f"Directory does not exist: {dir_path}")
                    continue
                
                # Run the indexing
                try:
                    await loop.run_in_executor(None, self.indexer.index, dir_path)
                    new_embeddings_created = True
                    self.progress_label.setText(f"Completed: {dir_path}")
                except Exception as e:
                    self.error(f"Error indexing {dir_path}: {str(e)}", exc_info=e)
                    self.progress_label.setText(f"Error with {dir_path}: {str(e)}")
                    continue
                
                # Update progress after each directory
                self.progress_bar.setValue(int(((i + 1) / total_dirs) * 100))
                await asyncio.sleep(0.1)  # Let the UI update
            
            self.progress_bar.setValue(100)
            self.progress_label.setText("Indexing completed successfully!")
            
            # Reload embeddings info in this dialog
            self.reload_embeddings_info()
            
            # Notify user
            QMessageBox.information(self, "Indexing Complete", 
                                  "All directories have been indexed successfully.")
            
            # If we have a parent viewer and new embeddings were created, 
            # suggest the user to refresh the embeddings
            parent = self.parent()
            if new_embeddings_created and parent and hasattr(parent, 'reload_embeddings'):
                reply = QMessageBox.question(
                    self, 
                    "Refresh Embeddings", 
                    "Would you like to refresh the embeddings in the viewer to include the newly indexed images?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    # Just call sync reload instead of async to avoid nested task issues
                    parent.reload_embeddings()
                    if hasattr(parent, 'search_and_update_gallery'):
                        # Create a task but don't wait for it
                        asyncio.create_task(parent.search_and_update_gallery())
            
        except Exception as e:
            self.error(f"Error during indexing: {str(e)}", exc_info=e)
            self.progress_label.setText(f"Error: {str(e)}")
            QMessageBox.critical(self, "Indexing Error", f"An error occurred during indexing:\n{str(e)}")
        finally:
            # Re-enable UI elements if dialog still exists
            try:
                self.index_button.setEnabled(True)
                self.add_dir_button.setEnabled(True)
                self.remove_dir_button.setEnabled(True)
                self.model_combo.setEnabled(True)
                self.close_button.setEnabled(True)  # Re-enable close button
            except RuntimeError as e:
                # Dialog might have been closed, ignore
                self.debug(f"Dialog closed during indexing: {str(e)}")
                pass

    def closeEvent(self, event):
        """Handle dialog close event by ensuring any pending tasks are finished."""
        if self.pending_task and not self.pending_task.done():
            self.warning("Dialog closing while indexing task is running")
            # Let the task finish but detach it from the dialog
            self.pending_task.add_done_callback(self._cleanup_on_task_done)
        
        super().closeEvent(event)
    
    def _cleanup_on_task_done(self, future):
        """Callback when a detached task is done - just handle exceptions."""
        try:
            future.result()  # This will raise any exception that occurred
        except Exception as e:
            self.error(f"Detached indexing task failed: {str(e)}", exc_info=e)

    def _start_indexing_clicked(self):
        """Handle click on Start Indexing button by creating and storing the task."""
        # Create the task and store it so we can check its status later
        self.pending_task = asyncio.create_task(self.start_indexing())
        # Add a callback so we know when it's done
        self.pending_task.add_done_callback(self._indexing_task_done)
    
    def _indexing_task_done(self, future):
        """Handle completion of the indexing task."""
        try:
            future.result()  # This will raise any exception that occurred
            self.debug("Indexing task completed successfully")
        except Exception as e:
            self.error(f"Indexing task failed: {str(e)}", exc_info=e)
        finally:
            self.pending_task = None  # Clear the pending task


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
                message
            )
        else:
            QMessageBox.information(
                self, 
                "No Embeddings Found", 
                "No embedding files were found in the embeddings directory."
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
