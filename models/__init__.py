from models.clip import CLIPModelWrapper


class CLIP:
    OpenAIBasePatch16 = CLIPModelWrapper(name="openai/clip-vit-base-patch16")
    OpenAILargePatch14 = CLIPModelWrapper(name="openai/clip-vit-large-patch14")
    OpenAILargePatch14_336 = CLIPModelWrapper(name="openai/clip-vit-large-patch14-336", batch_size=256, resize=336)
    LaionH14 = CLIPModelWrapper(name="laion/CLIP-ViT-H-14-laion2B-s32B-b79K")

    @classmethod
    def get_mapping(cls):
        return {
            "LaionH14": cls.LaionH14,
            "OpenAILargePatch14": cls.OpenAILargePatch14,
            "OpenAILargePatch14_336": cls.OpenAILargePatch14_336,
            "OpenAIBasePatch16": cls.OpenAIBasePatch16,
        }

    @classmethod
    def get_by_name(cls, name: str):
        return cls.get_mapping().get(name, CLIP.LaionH14)
