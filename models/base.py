from abc import ABC
from typing import Generic, TypeVar
import sys
import torch

from utils.lazy import Lazy

_TModel = TypeVar('_TModel')
_TProcessor = TypeVar('_TProcessor')


def get_best_device() -> str:
    """
    Determine the best available device for PyTorch.
    Returns 'mps' on Apple Silicon Macs if available,
    'cuda' if CUDA is available, otherwise 'cpu'.
    """
    if sys.platform == "darwin" and torch.backends.mps.is_available():
        return 'mps'
    elif torch.cuda.is_available():
        return 'cuda'
    return 'cpu'


class ModelWrapperBase(ABC, Generic[_TModel, _TProcessor]):
    def __init__(self, name: str):
        self.device = get_best_device()
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
