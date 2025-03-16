import os
from typing import Dict, List

# noinspection PyPackageRequirements
import torch
from PIL import Image, UnidentifiedImageError
# noinspection PyPackageRequirements
from torch import Tensor
# noinspection PyPackageRequirements
from torchvision import transforms
from transformers import CLIPProcessor, CLIPModel

from config import MODELS_DIR
from models.base import ModelWrapperBase


def is_image_file(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif'])


class CLIPModelWrapper(ModelWrapperBase[CLIPModel, CLIPProcessor]):
    def __init__(self, name: str, resize: int = 224, batch_size: int = 768):
        """
        Initialize CLIP model

        Args:
            name (str): Model name
            resize (int): Image resize size. Defaults to 224. Use 336 for 336 models, other 224
            batch_size (int): Number of images to process in a batch. Defaults to 768. Use 256 batch size for 336 models, other 768
        """
        ModelWrapperBase.__init__(self, name)
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
            print(f"Error loading image file '{image_path}': {e}")
            return None

    def create_image_embeddings(self, image_folder: str) -> Dict[str, Tensor]:
        image_paths = [os.path.join(image_folder, file) for file in os.listdir(image_folder) if is_image_file(file)]
        return self.create_image_embeddings_from_paths(image_paths)

    # noinspection PyTypeChecker
    def create_image_embeddings_from_paths(self, image_paths: List[str]) -> Dict[str, Tensor]:
        image_embeddings = dict()
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

            finally:
                del batch_images, batch_image_features
                if self.device == 'cuda':
                    torch.cuda.empty_cache()  # Clear GPU memory

        return image_embeddings

    def search_images_by_text(
            self,
            image_embeddings: dict[str, torch.Tensor],
            text_query: str
    ) -> list[tuple[str, float]]:
        # Encode the text query
        inputs = self.processor(text_query, return_tensors="pt")
        text_features = self.model.get_text_features(**inputs)
        text_features = text_features.unsqueeze(0)  # Add a batch dimension

        # image search
        similarity_scores = {}
        for image_path, image_features in image_embeddings.items():
            image_features = image_features.unsqueeze(0)  # Add a batch dimension
            similarity_score = torch.nn.functional.cosine_similarity(image_features, text_features)
            similarity_score = similarity_score.mean().item()  # Compute mean similarity score
            similarity_scores[image_path] = similarity_score

        # Sort images based on similarity scores
        sorted_images = sorted(similarity_scores.items(), key=lambda item: item[1], reverse=True)

        return sorted_images
