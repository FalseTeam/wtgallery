import asyncio
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QCursor
from PySide6.QtWidgets import QLineEdit, QLabel, QMenu, QApplication

from utils.logged import Logged


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
