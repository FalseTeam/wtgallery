import os
from pathlib import Path

# noinspection PyPackageRequirements
import torch

from models import CLIP
from models.base import ProgressCallback
from utils.loggerext import LoggerExt
from utils.validator import is_image_file


class Indexer(LoggerExt):

    def __init__(self, clip_model=CLIP.LaionH14):
        LoggerExt.__init__(self)
        self.clip_model_wrapper = clip_model

    @staticmethod
    def scan_directory(image_folder: str, include_subdirs: bool = True):
        if include_subdirs:
            images = list()
            for root, _, files in os.walk(image_folder):
                for file in files:
                    if is_image_file(file):
                        images.append(os.path.join(root, file))
        else:
            images = [os.path.join(image_folder, file) for file in os.listdir(image_folder) if is_image_file(file)]
        return images

    def create_image_embeddings(
            self,
            image_folders: list[str],
            include_subdirs: bool = True,
            progress_callback: ProgressCallback = None
    ) -> dict[str, torch.Tensor]:
        """
        Create embeddings for all images in the given folder and optionally its subdirectories.
        """
        image_paths = [
            image_path
            for image_folder in image_folders
            for image_path in self.scan_directory(image_folder, include_subdirs)
        ]
        return self.clip_model_wrapper.create_image_embeddings_from_paths(image_paths, progress_callback)

    def search_images_by_text(
            self,
            image_embeddings: dict[str, torch.Tensor],
            text_query: str
    ) -> list[tuple[str, float]]:
        """
        Search for images in the given image embeddings that are most similar to the given text query.

        Args:
            image_embeddings (dict[str, torch.Tensor]): Dictionary mapping image paths to their respective embeddings.
            text_query (str): Text query to search for.

        Returns:
            list[tuple[str, float]]: List of tuples, where each tuple contains the image path and its similarity score to the text query.
        """
        return self.clip_model_wrapper.search_images_by_text(image_embeddings, text_query)

    def search_images_by_image(
            self,
            image_embeddings: dict[str, torch.Tensor],
            query_image_path: str
    ) -> list[tuple[str, float]]:
        """
        Search for images in the given image embeddings that are most similar to the given query image.

        Args:
            image_embeddings (dict[str, torch.Tensor]): Dictionary mapping image paths to their respective embeddings.
            query_image_path (str): Path to the query image.

        Returns:
            list[tuple[str, float]]: List of tuples, where each tuple contains the image path and its similarity score to the query image.
        """
        return self.clip_model_wrapper.search_images_by_image(image_embeddings, query_image_path)

    def update_image_embeddings(
            self,
            existing_embeddings: dict[str, torch.Tensor],
            image_folders: list[str],
            include_subdirs: bool = True,
            progress_callback: ProgressCallback = None
    ) -> dict[str, torch.Tensor]:
        """
        Update image embeddings by processing new images in the specified folder.
        Returns:
            dict[str, torch.Tensor]: Updated dictionary of image embeddings including new images.
        """
        current_image_paths = set(existing_embeddings.keys())

        new_image_paths = [
            image_path
            for image_folder in image_folders
            for image_path in self.scan_directory(image_folder, include_subdirs)
        ]

        # Find the images that need to be added to the existing embeddings
        images_to_add = set(new_image_paths) - current_image_paths

        if not images_to_add:
            self.info("No new images to be processed")
            return existing_embeddings

        self.info(f"Found {len(images_to_add)} new images to be processed")

        new_embeddings = self.clip_model_wrapper.create_image_embeddings_from_paths(
            list(images_to_add), progress_callback
        )

        # Merge the existing and new embeddings
        updated_embeddings = {**existing_embeddings, **new_embeddings}
        self.info(f"Updated image embeddings from {len(existing_embeddings)} to {len(updated_embeddings)}")

        return updated_embeddings

    @staticmethod
    def save_image_embeddings(image_embeddings: dict[str, torch.Tensor], save_path: str | Path) -> None:
        torch.save(image_embeddings, str(save_path))

    @staticmethod
    def load_image_embeddings(load_path: str | Path) -> dict[str, torch.Tensor]:
        image_embeddings = torch.load(str(load_path))
        return image_embeddings

    def index(self,
              image_folders: list[str | Path],
              include_subdirs: bool = True,
              progress_callback: ProgressCallback = None):
        """
        Index images in the given folder and optionally its subdirectories.
        """

        not_found_count = 0

        for image_folder in image_folders:
            image_folder = Path(image_folder)
            if not image_folder.is_dir():
                not_found_count += 1
                self.warning(f"Directory not found: {image_folder}")

        if len(image_folders) == not_found_count:
            self.warning("No processable directories found")
            return

        embeddings_path = self.clip_model_wrapper.filepath
        if embeddings_path.exists():
            embeddings = self.load_image_embeddings(embeddings_path)
            image_embeddings = self.update_image_embeddings(
                embeddings, image_folders, include_subdirs, progress_callback
            )
            self.save_image_embeddings(image_embeddings, embeddings_path)
            self.info(f"Updated embeddings and saved to {embeddings_path}")
        else:
            image_embeddings = self.create_image_embeddings(
                image_folders, include_subdirs, progress_callback
            )
            self.save_image_embeddings(image_embeddings, embeddings_path)
            self.info(f"Created embeddings and saved to {embeddings_path}")
