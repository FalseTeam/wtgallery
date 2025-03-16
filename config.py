from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

DATA_DIR = PROJECT_DIR / "data"
MODELS_DIR = DATA_DIR / "models"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"

for _dir in [DATA_DIR, MODELS_DIR, EMBEDDINGS_DIR]:
    _dir.mkdir(exist_ok=True, parents=True)
