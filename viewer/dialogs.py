import asyncio
import datetime
from pathlib import Path

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
    QCheckBox,
)

from config import EMBEDDINGS_DIR
from indexer import Indexer
from utils.logged import Logged


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

        # Add total images count label
        self.total_images_label = QLabel("Total: 0 images across 0 embedding files")
        layout.addWidget(self.total_images_label)

        self.embeddings_info = QListWidget()
        self.embeddings_info.setMaximumHeight(150)
        # self.embeddings_info.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)  # Enable multiple selection
        layout.addWidget(self.embeddings_info)

        # Add remove embeddings button
        self.remove_embeddings_button = QPushButton("Remove Selected Embeddings")
        self.remove_embeddings_button.clicked.connect(self.remove_selected_embeddings)
        layout.addWidget(self.remove_embeddings_button)

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

        # Subdirectories checkbox
        self.include_subdirs_checkbox = QCheckBox("Include subdirectories")
        self.include_subdirs_checkbox.setChecked(True)  # Default to True
        layout.addWidget(self.include_subdirs_checkbox)

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
                self.total_images_label.setText("Total: 0 images across 0 embedding files")
                self.embeddings_info.addItem("No embeddings directory found. It will be created when indexing.")
                return

            # Get all embedding files
            embeddings_files = list(EMBEDDINGS_DIR.glob("*.pt"))

            if not embeddings_files:
                self.total_images_label.setText("Total: 0 images across 0 embedding files")
                self.embeddings_info.addItem("No embeddings found.")
                return

            total_images = 0
            source_stats = {}

            for file in embeddings_files:
                try:
                    # Load embeddings to get count and paths
                    embeddings = self.indexer.load_image_embeddings(str(file))
                    num_images = len(embeddings)
                    total_images += num_images

                    # Extract info from filename
                    source_info = file.stem  # filename without extension
                    source_stats[source_info] = num_images

                    # Extract unique directories from image paths
                    unique_dirs = set()
                    for image_path in embeddings.keys():
                        dir_path = str(Path(image_path).parent)
                        unique_dirs.add(dir_path)

                    # Format directory info
                    dir_info = " (" + ', '.join(unique_dirs) + ")"

                    # Add to list with image count and directory info
                    self.embeddings_info.addItem(f"{source_info}: {num_images} images{dir_info}")
                except Exception as e:
                    error_msg = f"{file.name}: Error loading ({str(e)})"
                    self.embeddings_info.addItem(error_msg)
                    self.error(error_msg, exc_info=e)

            # Update the total images label
            self.total_images_label.setText(
                f"Total: {total_images} images across {len(embeddings_files)} embedding files")

        except Exception as e:
            error_msg = f"Error loading embeddings info: {str(e)}"
            self.error(error_msg, exc_info=e)
            self.total_images_label.setText("Total: Error loading embeddings")
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
                    include_subdirs = self.include_subdirs_checkbox.isChecked()

                    # Create a filename that includes directory information
                    dir_path_obj = Path(dir_path)
                    if include_subdirs:
                        # If including subdirs, use the base directory name
                        filename = dir_path_obj.name
                    else:
                        # If not including subdirs, use the full path with __ separators
                        filename = '__'.join(dir_path_obj.parts)

                    # Set the output filename in the indexer
                    self.indexer.output_filename = filename

                    await loop.run_in_executor(None, self.indexer.index, dir_path, include_subdirs)
                    new_embeddings_created = True
                    self.progress_label.setText(f"Completed: {dir_path}")

                    # Save metadata about indexed directories
                    import json
                    metadata_file = EMBEDDINGS_DIR / f"{Path(dir_path).name}.meta.json"
                    metadata = {
                        'indexed_directories': [dir_path],
                        'include_subdirs': include_subdirs,
                        'model': model_key,
                        'timestamp': str(datetime.datetime.now())
                    }

                    # If metadata file exists, merge with existing data
                    if metadata_file.exists():
                        with open(metadata_file, 'r') as f:
                            existing_metadata = json.load(f)
                            # Add new directory if not already present
                            if dir_path not in existing_metadata.get('indexed_directories', []):
                                existing_metadata['indexed_directories'].append(dir_path)
                            # Update other fields
                            existing_metadata.update({
                                'include_subdirs': include_subdirs,
                                'model': model_key,
                                'timestamp': str(datetime.datetime.now())
                            })
                            metadata = existing_metadata

                    # Save the metadata
                    with open(metadata_file, 'w') as f:
                        json.dump(metadata, f, indent=2)

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
                                    "All directories have been indexed successfully.",
                                    QMessageBox.StandardButton.Ok)

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

    def remove_selected_embeddings(self):
        """Remove selected embedding files and update the list."""
        selected_items = self.embeddings_info.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select embeddings to remove.")
            return

        # Skip the first item if it's the summary
        items_to_remove = []
        for item in selected_items:
            text = item.text()
            if not text.startswith("Total:"):  # Skip the summary line
                # Extract the source info (everything before the colon)
                source_info = text.split(":")[0]
                items_to_remove.append(source_info)

        if not items_to_remove:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Are you sure you want to remove {len(items_to_remove)} embedding file(s)?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            for source_info in items_to_remove:
                try:
                    # Find and remove the embedding file
                    embedding_file = EMBEDDINGS_DIR / f"{source_info}.pt"
                    if embedding_file.exists():
                        embedding_file.unlink()
                        self.info(f"Removed embedding file: {embedding_file}")
                    else:
                        self.warning(f"Embedding file not found: {embedding_file}")
                except Exception as e:
                    self.error(f"Error removing embedding file {source_info}: {str(e)}", exc_info=e)

            # Reload the embeddings info to update the display
            self.load_embeddings_info()
