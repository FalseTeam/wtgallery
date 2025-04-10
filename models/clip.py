import os
import re
from typing import Dict, List

# noinspection PyPackageRequirements
import torch
from PIL import Image, UnidentifiedImageError
# noinspection PyPackageRequirements
from torch import Tensor
# noinspection PyPackageRequirements
from torchvision import transforms
from transformers import CLIPProcessor, CLIPModel

from config import MODELS_DIR, EMBEDDINGS_DIR
from models.base import ModelWrapperBase, ProgressCallback
from utils.loggerext import LoggerExt
from utils.validator import is_image_file

# Disable the limit by setting it to None
# Or increase it to a higher value, e.g.
# Image.MAX_IMAGE_PIXELS = 300000000  # 300 million pixels
Image.MAX_IMAGE_PIXELS = None


class CLIPModelWrapper(ModelWrapperBase[CLIPModel, CLIPProcessor], LoggerExt):
    def __init__(self, name: str, resize: int = 224, batch_size: int = 768):
        """
        Initialize CLIP model

        Args:
            name (str): Model name
            resize (int): Image resize size. Defaults to 224. Use 336 for 336 models, other 224
            batch_size (int): Number of images to process in a batch. Defaults to 768. Use 256 batch size for 336 models, other 768
        """
        ModelWrapperBase.__init__(self, name)
        LoggerExt.__init__(self)
        self.resize = resize
        self.batch_size = batch_size

    def load_model(self):
        return CLIPModel.from_pretrained(self.name, cache_dir=MODELS_DIR)

    def load_processor(self):
        return CLIPProcessor.from_pretrained(self.name, cache_dir=MODELS_DIR)

    def load_image(self, image_path: str) -> Tensor | None:
        try:
            # Load and preprocess an image
            image = Image.open(image_path).convert("RGB")  # Convert to RGB format
            transform = transforms.Compose([
                transforms.Resize((self.resize, self.resize)),
                transforms.ToTensor(),
            ])
            image = transform(image)
            image = image.unsqueeze(0)

            # Normalize the image to the range [0, 1]
            image = image.clamp(0.0, 1.0)

            return image
        except UnidentifiedImageError as e:
            self.warning(f"Error loading: {e}")
            return None

    def create_image_embeddings(self, image_folder: str) -> Dict[str, Tensor]:
        image_paths = [os.path.join(image_folder, file) for file in os.listdir(image_folder) if is_image_file(file)]
        return self.create_image_embeddings_from_paths(image_paths)

    def search_images_by_text(
            self,
            image_embeddings: dict[str, torch.Tensor],
            text_query: str
    ) -> list[tuple[str, float]]:
        try:
            # Encode the text query
            inputs = self.processor(text_query, return_tensors="pt")
            # Move inputs to the correct device
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            # Get text features on the correct device
            text_features = self.model.to(self.device).get_text_features(**inputs)
            text_features = text_features.unsqueeze(0)  # Add a batch dimension

            # image search
            similarity_scores = {}
            for image_path, image_features in image_embeddings.items():
                # Move image features to the same device as text features
                image_features = image_features.to(self.device).unsqueeze(0)  # Add a batch dimension
                similarity_score = torch.nn.functional.cosine_similarity(image_features, text_features)
                similarity_score = similarity_score.mean().item()  # Compute mean similarity score
                similarity_scores[image_path] = similarity_score

            # Sort images based on similarity scores
            sorted_images = sorted(similarity_scores.items(), key=lambda item: item[1], reverse=True)

            return sorted_images
        finally:
            # Clean up GPU memory regardless of device type
            if self.device != 'cpu':
                torch.cuda.empty_cache()

    def search_images_by_image(
            self,
            image_embeddings: dict[str, torch.Tensor],
            query_image_path: str
    ) -> list[tuple[str, float]]:
        """
        Search for similar images using an image as the query.

        Args:
            image_embeddings (dict[str, torch.Tensor]): Dictionary mapping image paths to their respective embeddings.
            query_image_path (str): Path to the query image.

        Returns:
            list[tuple[str, float]]: List of tuples, where each tuple contains the image path and its similarity score to the query image.
        """
        try:
            # Load and get features for the query image
            query_image = self.load_image(query_image_path)
            if query_image is None:
                return []

            query_image = query_image.to(self.device)

            with torch.no_grad():
                query_features = self.model.to(self.device).get_image_features(pixel_values=query_image)

            # image search
            similarity_scores = {}
            for image_path, image_features in image_embeddings.items():
                if image_path == query_image_path:  # Skip the query image itself
                    continue

                # Move image features to the same device as query features
                image_features = image_features.to(self.device)
                # Calculate cosine similarity
                similarity_score = torch.nn.functional.cosine_similarity(image_features.unsqueeze(0), query_features)
                similarity_score = similarity_score.mean().item()
                similarity_scores[image_path] = similarity_score

            # Sort images based on similarity scores
            sorted_images = sorted(similarity_scores.items(), key=lambda item: item[1], reverse=True)

            return sorted_images
        finally:
            # Clean up GPU memory regardless of device type
            if self.device != 'cpu':
                torch.cuda.empty_cache()

    # noinspection PyTypeChecker
    def create_image_embeddings_from_paths(
            self,
            image_paths: List[str],
            progress_callback: ProgressCallback = None
    ) -> Dict[str, Tensor]:
        image_embeddings = dict()

        total = len(image_paths)
        current = 0
        progress_callback(current, total)

        for i in range(0, len(image_paths), self.batch_size):
            # noinspection PyUnusedLocal
            batch_images, batch_image_features = None, None

            try:
                batch_image_paths = image_paths[i:i + self.batch_size]
                _batch_images = [self.load_image(image_path) for image_path in batch_image_paths]
                batch_images = [image for image in _batch_images if image is not None]  # Exclude None values

                if not batch_images:
                    continue  # Skip empty batches

                batch_images = torch.cat([image.to(self.device) for image in batch_images], dim=0)

                with torch.no_grad():
                    # noinspection PyTypeChecker
                    batch_image_features = self.model.to(self.device).get_image_features(pixel_values=batch_images)

                for j, image_path in enumerate(batch_image_paths[:len(batch_images)]):
                    if batch_images[j] is not None:
                        image_embeddings[image_path] = batch_image_features[j].cpu()

                current += len(batch_image_paths)
                progress_callback(current, total)

            finally:
                del batch_images, batch_image_features
                # Clean up GPU memory regardless of device type
                if self.device != 'cpu':
                    torch.cuda.empty_cache()

        return image_embeddings

    @property
    def filepath(self):
        return EMBEDDINGS_DIR.joinpath(re.sub(r'[ ,.:()\[\]{}\\/]+', '-', self.name)).with_suffix('.pt')
