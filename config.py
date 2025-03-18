import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

DATA_DIR = os.getenv('DATA_DIR', PROJECT_DIR / "data")
MODELS_DIR = DATA_DIR / "models"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"

LOGS_DIR = Path(os.getenv('LOGS_DIR', DATA_DIR / 'log'))
LOG_LEVEL = int(os.getenv('LOG_LEVEL', 0))

for _dir in [DATA_DIR, MODELS_DIR, EMBEDDINGS_DIR, LOGS_DIR]:
    _dir.mkdir(exist_ok=True, parents=True)
