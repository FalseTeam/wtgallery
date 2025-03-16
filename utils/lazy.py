from typing import TypeVar, Generic, Callable

_T = TypeVar('_T')


class Lazy(Generic[_T]):
    def __init__(self, factory: Callable[[], _T]):
        self._factory: Callable[[], _T] = factory
        self._value: _T | None = None

    def get(self) -> _T:
        if self._value is None:
            self._value = self._factory()
        return self._value

    def __call__(self) -> _T:
        return self.get()
