import os
import re
import sys
from pathlib import Path

# noinspection PyPackageRequirements
import torch

from config import EMBEDDINGS_DIR
from models import CLIP


def is_image_file(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif'])


class Indexer:

    def __init__(self, clip_model=CLIP.LaionH14):
        self.clip_model_wrapper = clip_model

    def create_image_embeddings(self, image_folder: str) -> dict[str, torch.Tensor]:
        return self.clip_model_wrapper.create_image_embeddings(image_folder)

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
            image_folder: str
    ) -> dict[str, torch.Tensor]:
        """
        Update image embeddings by processing new images in the specified folder.

        Args:
            existing_embeddings (dict[str, torch.Tensor]): Current image embeddings.
            image_folder (str): Path to the folder containing images.

        Returns:
            dict[str, torch.Tensor]: Updated dictionary of image embeddings including new images.
        """
        current_image_paths = set(existing_embeddings.keys())
        new_image_paths = {os.path.join(image_folder, file) for file in os.listdir(image_folder) if is_image_file(file)}

        # Find the images that need to be added to the existing embeddings
        images_to_add = new_image_paths - current_image_paths

        if not images_to_add:
            print("No new images to be processed")
            return existing_embeddings

        print(f"Found {len(images_to_add)} new images to be processed")

        new_embeddings = self.clip_model_wrapper.create_image_embeddings_from_paths(list(images_to_add))

        # Merge the existing and new embeddings
        updated_embeddings = {**existing_embeddings, **new_embeddings}
        print(f"Updated image embeddings from {len(existing_embeddings)} to {len(updated_embeddings)}")

        return updated_embeddings

    @staticmethod
    def save_image_embeddings(image_embeddings: dict[str, torch.Tensor], save_path: str) -> None:
        torch.save(image_embeddings, save_path)

    @staticmethod
    def load_image_embeddings(load_path: str) -> dict[str, torch.Tensor]:
        image_embeddings = torch.load(load_path)
        return image_embeddings

    def index(self, image_folder: str):
        print(f"Processing {image_folder}")
        embeddings_name = re.sub(
            pattern=r'[ ,.:()\[\]{}\\/]+', repl='-',
            string=f"{image_folder}"
                   f"_{self.clip_model_wrapper.name}"
                   f"_{self.clip_model_wrapper.device}"
                   f"_batch-{self.clip_model_wrapper.batch_size}",
        )
        embeddings_path = EMBEDDINGS_DIR.joinpath(embeddings_name).with_suffix('.pt')

        if embeddings_path.exists():
            embeddings = self.load_image_embeddings(embeddings_path.__str__())
            image_embeddings = self.update_image_embeddings(embeddings, image_folder.__str__())
            self.save_image_embeddings(image_embeddings, embeddings_path.__str__())
            print(f"Updated embeddings and saved to {embeddings_path}")

        else:
            image_embeddings = self.create_image_embeddings(image_folder.__str__())
            self.save_image_embeddings(image_embeddings, embeddings_path.__str__())
            print(f"Created embeddings and saved to {embeddings_path}")


def main():
    indexer = Indexer()

    for image_folder in [Path(p) for p in sys.argv if Path(p).is_dir()]:
        indexer.index(image_folder.__str__())

    print("Done")


if __name__ == "__main__":
    main()
