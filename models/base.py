from abc import ABC
from typing import Generic, TypeVar

from utils.lazy import Lazy

_TModel = TypeVar('_TModel')
_TProcessor = TypeVar('_TProcessor')


class ModelWrapperBase(ABC, Generic[_TModel, _TProcessor]):
    def __init__(self, name: str):
        self.device = 'cuda'
        self.name = name
        self.__model: Lazy[_TModel] = Lazy(self.load_model)
        self.__processor: Lazy[_TProcessor] = Lazy(self.load_processor)

    @property
    def model(self) -> _TModel:
        return self.__model()

    @property
    def processor(self) -> _TProcessor:
        return self.__processor()

    def load_model(self):
        ...

    def load_processor(self):
        ...
