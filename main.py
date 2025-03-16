import os
import torch
from PIL import Image, UnidentifiedImageError
from torchvision import transforms
from transformers import CLIPProcessor, CLIPModel

# CLIP_MODEL = 'openai/clip-vit-base-patch16'
CLIP_MODEL = 'openai/clip-vit-large-patch14'
# CLIP_MODEL = 'openai/clip-vit-large-patch14-336'  # use 256 batch size
# CLIP_MODEL = 'laion/CLIP-ViT-H-14-laion2B-s32B-b79K'

model = CLIPModel.from_pretrained(CLIP_MODEL)
processor = CLIPProcessor.from_pretrained(CLIP_MODEL)


def load_image(image_path):
    try:
        # Load and preprocess an image
        image = Image.open(image_path).convert("RGB")  # Convert to RGB format
        transform = transforms.Compose([
            transforms.Resize((224, 224)),  # 336 for 336 models, other 224
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


def create_image_embeddings(image_folder, batch_size=768, device='cuda'):
    # Load the CLIP model
    model = CLIPModel.from_pretrained(CLIP_MODEL).to(device)

    image_embeddings = {}
    image_paths = [os.path.join(image_folder, file) for file in os.listdir(image_folder) if is_image_file(file)]

    for i in range(0, len(image_paths), batch_size):
        batch_image_paths = image_paths[i:i + batch_size]
        batch_images = [load_image(image_path) for image_path in batch_image_paths]
        batch_images = [image for image in batch_images if image is not None]  # Exclude None values

        if not batch_images:
            continue  # Skip empty batches

        batch_images = torch.cat([image.to(device) for image in batch_images], dim=0)

        with torch.no_grad():
            batch_image_features = model.get_image_features(pixel_values=batch_images)

        for j, image_path in enumerate(batch_image_paths[:len(batch_images)]):
            if batch_images[j] is not None:
                image_embeddings[image_path] = batch_image_features[j].cpu()

        del batch_images, batch_image_features
        torch.cuda.empty_cache()  # Clear GPU memory

    return image_embeddings


def is_image_file(filename):
    return any(filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif'])


def search_images_by_text(image_embeddings, text_query):
    # Encode the text query
    inputs = processor(text_query, return_tensors="pt")
    text_features = model.get_text_features(**inputs)
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


def save_image_embeddings(image_embeddings, save_path):
    torch.save(image_embeddings, save_path)


def load_image_embeddings(load_path):
    image_embeddings = torch.load(load_path)
    return image_embeddings


def update_image_embeddings(existing_embeddings, image_folder, batch_size=768, device='cuda'):
    current_image_paths = set(existing_embeddings.keys())
    new_image_paths = {os.path.join(image_folder, file) for file in os.listdir(image_folder) if is_image_file(file)}

    # Find the images that need to be added to the existing embeddings
    images_to_add = new_image_paths - current_image_paths

    if not images_to_add:
        print("No new images to be processed")
        return existing_embeddings

    print(f"Found {len(images_to_add)} new images to be processed")

    new_embeddings = create_image_embeddings_from_paths(list(images_to_add), batch_size, device)

    # Merge the existing and new embeddings
    updated_embeddings = {**existing_embeddings, **new_embeddings}
    print(f"Updated image embeddings from {len(existing_embeddings)} to {len(updated_embeddings)}")

    return updated_embeddings


def create_image_embeddings_from_paths(image_paths, batch_size=768, device='cuda'):
    image_embeddings = {}
    model = CLIPModel.from_pretrained(CLIP_MODEL).to(device)
    for i in range(0, len(image_paths), batch_size):
        batch_image_paths = image_paths[i:i + batch_size]
        batch_images = [load_image(image_path) for image_path in batch_image_paths]
        batch_images = [image for image in batch_images if image is not None]  # Exclude None values

        if not batch_images:
            continue  # Skip empty batches

        batch_images = torch.cat([image.to(device) for image in batch_images], dim=0)

        with torch.no_grad():
            batch_image_features = model.get_image_features(pixel_values=batch_images)

        for j, image_path in enumerate(batch_image_paths[:len(batch_images)]):
            if batch_images[j] is not None:
                image_embeddings[image_path] = batch_image_features[j].cpu()

        del batch_images, batch_image_features
        torch.cuda.empty_cache()  # Clear GPU memory

    return image_embeddings


# Example of usage
# updated_embeddings = update_image_embeddings(image_embeddings, image_folder)
# save_image_embeddings(updated_embeddings, "updated_embeddings.pt")

if __name__ == "__main__":
    image_folder = "D:\\tg_fox_dump"

    image_embeddings = create_image_embeddings(image_folder)
    save_image_embeddings(image_embeddings, "tg_fox_dump_large14_cpu_batch_768.pt")
    print("created embeddings")
