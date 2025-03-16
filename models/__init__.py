from models.clip import CLIPModelWrapper


class CLIP:
    OpenAIBasePatch16 = CLIPModelWrapper(name="openai/clip-vit-base-patch16")
    OpenAILargePatch14 = CLIPModelWrapper(name="openai/clip-vit-large-patch14")
    OpenAILargePatch14_336 = CLIPModelWrapper(name="openai/clip-vit-large-patch14-336", batch_size=256, resize=336)
    LaionH14 = CLIPModelWrapper(name="laion/CLIP-ViT-H-14-laion2B-s32B-b79K")
