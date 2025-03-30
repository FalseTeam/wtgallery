import asyncio
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QProgressBar,
    QMessageBox,
    QFileDialog,
    QCheckBox, QWidget,
)
from tqdm import tqdm

from config import EMBEDDINGS_DIR
from indexer import Indexer
from models import CLIP
from utils.io_utils import run_in_background
from utils.lazy import LazyParameterized
from utils.loggerext import LoggerExt
from viewer.base import ImageViewerExt


class IndexerSettingsDialog(QDialog, LoggerExt, ImageViewerExt):
    def __init__(self, parent: QWidget, indexer: Indexer):
        QDialog.__init__(self, parent)
        ImageViewerExt.__init__(self, parent)
        LoggerExt.__init__(self)

        self.indexer = indexer
        self.pending_task = None  # Track the running indexing task
        self.setWindowTitle("Indexer Settings")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        # Main layout
        layout = QVBoxLayout(self)

        # Model selection
        model_layout = QHBoxLayout()

        self.model_label = QLabel("CLIP Model:")
        model_layout.addWidget(self.model_label)

        self.model_combo = QComboBox()
        self.model_combo.addItem("laion/CLIP-ViT-H-14-laion2B-s32B-b79K", "LaionH14")
        self.model_combo.addItem("openai/clip-vit-large-patch14", "OpenAILargePatch14")
        self.model_combo.addItem("openai/clip-vit-large-patch14-336", "OpenAILargePatch14_336")
        self.model_combo.addItem("openai/clip-vit-base-patch16", "OpenAIBasePatch16")
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        model_layout.addWidget(self.model_combo)

        layout.addLayout(model_layout)

        # Directories list
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

        # Subdirectories checkbox
        self.include_subdirs_checkbox = QCheckBox("Include subdirectories")
        self.include_subdirs_checkbox.setChecked(True)  # Default to True
        layout.addWidget(self.include_subdirs_checkbox)

        # Progress bar
        self.progress_bar = QProgressBar(textVisible=False, minimum=0, maximum=100, value=0)
        layout.addWidget(self.progress_bar)

        # Progress indicator
        self.progress_label = QLabel("Ready")
        layout.addWidget(self.progress_label)

        # Buttons
        buttons_layout = QHBoxLayout()

        self.index_button = QPushButton("Start Indexing")
        self.index_button.clicked.connect(self._start_indexing_clicked)
        buttons_layout.addWidget(self.index_button)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        buttons_layout.addWidget(self.close_button)

        layout.addLayout(buttons_layout)

        self.on_model_changed()

    def on_model_changed(self):
        """Handle model selection change"""
        self.directories_list.clear()

        try:
            # Load embeddings to get directories
            if self.selected_model.filepath.exists():
                embeddings = self.indexer.load_image_embeddings(self.selected_model.filepath)

                # Extract unique directories from image paths
                unique_dirs = set()
                for image_path in embeddings.keys():
                    dir_path = str(Path(image_path).parent)
                    unique_dirs.add(dir_path)

                # Add directories to list
                for dir_path in sorted(unique_dirs):
                    self.directories_list.addItem(dir_path)

        except Exception as e:
            self.error(f"Error loading directories from file: {str(e)}", exc_info=e)

    def add_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            parent=self, caption="Select Directory to Index", dir=str(Path.home()),
            options=QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.ReadOnly | QFileDialog.Option.HideNameFilterDetails
        )
        if dir_path:
            dir_path = Path(dir_path)
            if dir_path.is_dir() and not self.directories_list.findItems(str(dir_path), Qt.MatchFlag.MatchExactly):
                self.directories_list.addItem(str(dir_path))

    def remove_directory(self):
        to_remove_dirs = set()
        for item in self.directories_list.selectedItems():
            to_remove_dirs.add(Path(item.text()))
            self.directories_list.takeItem(self.directories_list.row(item))

        # Load embeddings to get directories
        if self.selected_model.filepath.exists():
            embeddings = self.indexer.load_image_embeddings(self.selected_model.filepath)
            removed = False
            for image_path in list(embeddings.keys()):
                if Path(image_path).parent in to_remove_dirs:
                    embeddings.pop(image_path, None)
                    removed = True
            self.indexer.save_image_embeddings(embeddings, self.selected_model.filepath)

            if removed and QMessageBox.question(
                    self,
                    "Refresh Embeddings",
                    "Would you like to refresh the embeddings in the viewer to update indexed images?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
            ) == QMessageBox.StandardButton.Yes:
                # Just call sync reload instead of async to avoid nested task issues
                self.viewer.reload_embeddings()
                # Create a task but don't wait for it
                asyncio.create_task(self.viewer.search_and_update_gallery())

        self.on_model_changed()

    async def start_indexing(self):
        if self.directories_list.count() == 0:
            QMessageBox.warning(self, "No Directories", "Please add at least one directory to index.")
            return

        # Disable UI elements during indexing
        self.index_button.setEnabled(False)
        self.add_dir_button.setEnabled(False)
        self.remove_dir_button.setEnabled(False)
        self.model_combo.setEnabled(False)
        self.close_button.setEnabled(False)

        self.progress_label.setText("Indexing in progress...")
        self.progress_bar.setValue(0)

        self.info(f"Using CLIP model: {self.selected_model.name}")
        self.indexer = Indexer(clip_model=self.selected_model)

        # Also log the embeddings directory
        self.info(f"Embeddings will be saved to: {EMBEDDINGS_DIR}")

        # Ensure embeddings directory exists
        if not EMBEDDINGS_DIR.exists():
            self.info(f"Creating embeddings directory: {EMBEDDINGS_DIR}")
            EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

        # Process each directory
        new_embeddings_created = False

        try:
            total_dirs = self.directories_list.count()
            dir_paths = set(Path(self.directories_list.item(i).text()) for i in range(self.directories_list.count()))

            # Extract unique directories from image paths
            if self.selected_model.filepath.exists():
                embeddings = self.indexer.load_image_embeddings(self.selected_model.filepath)
                existing_dirs = set(Path(image_path).parent for image_path in embeddings.keys())

                to_delete = existing_dirs - dir_paths
                to_append = dir_paths - existing_dirs
            else:
                to_delete = set()
                to_append = set(dir_paths)

            pbar: LazyParameterized[tqdm, int] = LazyParameterized(lambda t: tqdm(unit='img', total=t, ncols=64))

            def progress_callback(current: int, total: int):
                nonlocal pbar
                pbar(total).update(current - pbar(total).pos)
                if self.progress_bar.maximum() != total:
                    self.progress_bar.setMaximum(total)
                if self.progress_bar.value() != current:
                    self.progress_bar.setValue(current)

            # Run the indexing
            try:
                include_subdirs = self.include_subdirs_checkbox.isChecked()
                await run_in_background(self.indexer.index, list(to_append), include_subdirs, progress_callback)
                new_embeddings_created = True
                self.progress_label.setText("Completed")

            except Exception as e:
                self.error(f"Error indexing: {str(e)}", exc_info=e)
                self.progress_label.setText(f"Error: {str(e)}")

            self.progress_bar.setValue(100)
            self.progress_label.setText("Indexing completed successfully!")

            # Notify user
            QMessageBox.information(self, "Indexing Complete",
                                    "All directories have been indexed successfully.",
                                    QMessageBox.StandardButton.Ok)

            # If we have a parent viewer and new embeddings were created, 
            # suggest the user to refresh the embeddings
            if new_embeddings_created:
                if QMessageBox.question(
                        self,
                        "Refresh Embeddings",
                        "Would you like to refresh the embeddings in the viewer to include the newly indexed images?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                ) == QMessageBox.StandardButton.Yes:
                    # Just call sync reload instead of async to avoid nested task issues
                    self.viewer.reload_embeddings()
                    # Create a task but don't wait for it
                    asyncio.create_task(self.viewer.search_and_update_gallery())

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

    @property
    def selected_model(self):
        return CLIP.get_by_name(self.model_combo.currentData())
