from abc import abstractmethod

from PySide6.QtCore import QObject

from utils.lazy import Lazy


class ImageViewerInterface:

    @abstractmethod
    async def search_and_update_gallery(self): ...

    @abstractmethod
    async def search_similar_images(self, query_image_path: str): ...

    @abstractmethod
    def reload_embeddings(self): ...

    @abstractmethod
    async def reload_embeddings_and_search(self): ...


class ImageViewerExt:
    def __init__(self, parent: QObject | None):
        self.__parent = parent
        self.__viewer = Lazy(self.__viewer_factory)

    @property
    def viewer(self) -> ImageViewerInterface:
        return self.__viewer()

    def __viewer_factory(self) -> ImageViewerInterface:
        parent = self.__parent
        if isinstance(parent, ImageViewerInterface):
            return parent
        while parent is not None:
            parent = parent.parent()
            if isinstance(parent, ImageViewerInterface):
                return parent
        raise ValueError("No ImageViewer parent found")
