# Usage

1. Launch `indexer.py` to create embeddings for all images in the specified folder. The embeddings will be saved in the
   `data/embeddings` folder.

2. Launch `viewer.py` to start the image viewer. The viewer will load the embeddings from the `data/embeddings` folder
   and allow you to search for images by text query.

```bash
python -m indexer path/to/dir1 path/to/dir2
python -m viewer
```
