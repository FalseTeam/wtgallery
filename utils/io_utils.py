import asyncio
import logging
import os
import random
import subprocess
import sys
import time
from asyncio import Future
from concurrent.futures import ThreadPoolExecutor, Executor
from functools import wraps
from typing import TypeVar, Callable, Coroutine, Any, Type, ParamSpec

_log = logging.getLogger('io')

_executor = ThreadPoolExecutor(4096, 'IO')

_P = ParamSpec('_P')
_R = TypeVar('_R')


def run(func: Callable[..., _R], *args) -> Future[_R]:
    return asyncio.get_running_loop().run_in_executor(_executor, func, *args)


def run_in_background(func: Callable[_P, _R], *args: _P.args) -> Future[_R]:
    return asyncio.get_running_loop().run_in_executor(_executor, func, *args)


async def arun_kw(func: Callable[_P, _R], *args: _P.args, **kwargs: _P.kwargs) -> _R:
    # noinspection PyTypeChecker
    return await asyncio.get_running_loop().run_in_executor(_executor, lambda: func(*args, **kwargs))


def run_coro(coro: Coroutine[Any, Any, _R]) -> Future[_R]:
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    fut = asyncio.get_running_loop().run_in_executor(_executor, loop.run_forever)
    asyncio.run_coroutine_threadsafe(coro, loop)
    return fut


async def arun_coro(coro: Coroutine[Any, Any, _R]) -> _R:
    loop = asyncio.new_event_loop()
    # noinspection PyTypeChecker
    fut = asyncio.get_running_loop().run_in_executor(_executor, loop.run_forever)
    asyncio.run_coroutine_threadsafe(coro, loop)
    return await fut


class Context:
    def __init__(self, fn: Callable[_P, _R], *args: _P.args, **kwargs: _P.kwargs):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.log = _log.getChild(fn.__name__)


def run_in_executor_with_retry(max_retries: int = 10,
                               sleep_time_base: float = 2,
                               sleep_time_max: float = 64,
                               jitter: int = 0,
                               *,
                               non_handling_errors: list[Type[Exception]] = None,
                               error_handler: Callable[[Exception, Context], None] = None,
                               executor: Executor = _executor):
    rnd = random.Random(time.time())

    def actual_decorator(fn: Callable[_P, _R]) -> Callable[_P, Coroutine[Any, Any, _R]]:
        log = _log.getChild(fn.__name__)

        @wraps(fn)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            def _func():
                for attempt in range(1, max_retries + 1):
                    try:
                        if jitter > 0:
                            _sleep_time: float = rnd.randint(0, jitter * 1000) / 1000
                            time.sleep(_sleep_time)
                        result = fn(*args, **kwargs)
                        if attempt > 1:
                            if log.level == logging.DEBUG:
                                _parameters = ', '.join(list(args) + [f'{k}={v}' for k, v in kwargs.items()])
                                log.info(f'Finished executing function {fn.__name__}({_parameters}) '
                                         f'after {attempt} attempts')
                            else:
                                log.info(f'Finished executing function {fn.__name__}() '
                                         f'after {attempt} attempts')
                        return result
                    except Exception as exc:
                        if non_handling_errors is not None:
                            for _exc_type in non_handling_errors:
                                if isinstance(exc, _exc_type):
                                    raise exc

                        if error_handler:
                            error_handler(exc, Context(fn, *args, **kwargs))

                        if attempt < max_retries:

                            _sleep_time: float = float(min(sleep_time_base ** attempt, sleep_time_max))
                            _jitter = (rnd.randint(-jitter * 1000, jitter * 1000) / 1000) if jitter > 0 else 0
                            _sleep_time = abs(_jitter) if _sleep_time + _jitter < 0 else _sleep_time + _jitter

                            if log.level == logging.DEBUG:
                                _parameters = ', '.join(list(args) + [f'{k}={v}' for k, v in kwargs.items()])
                                log.warning(f'Retry call {fn.__name__}({_parameters}) at {_sleep_time:.03f} seconds. '
                                            f'Reason: {exc.__class__.__qualname__}: {exc}. '
                                            f'Attempt: {attempt}')
                            else:
                                log.warning(f'Retry call {fn.__name__}() at {_sleep_time:.03f} seconds. '
                                            f'Reason: {exc.__class__.__qualname__}: {exc}. '
                                            f'Attempt: {attempt}')
                            time.sleep(_sleep_time)
                        else:
                            raise exc

            # noinspection PyTypeChecker
            return await asyncio.get_running_loop().run_in_executor(executor, _func)

        return wrapper

    return actual_decorator


def run_with_retry(max_retries: int = 1000,
                   sleep_time_base: float = 2,
                   sleep_time_max: float = 64,
                   jitter: int = 0,
                   *,
                   non_handling_errors: list[Type[Exception]] = None,
                   error_handler: Callable[[Exception, Context], None] = None):
    rnd = random.Random(time.time())

    def actual_decorator(fn: Callable[_P, _R]) -> Callable[_P, Coroutine[Any, Any, _R]]:
        log = _log.getChild(fn.__name__)

        @wraps(fn)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            def _func():
                for attempt in range(1, max_retries + 1):
                    try:
                        if jitter > 0:
                            _sleep_time: float = rnd.randint(0, jitter * 1000) / 1000
                            time.sleep(_sleep_time)
                        result = fn(*args, **kwargs)
                        if attempt > 1:
                            if log.level == logging.DEBUG:
                                _parameters = ', '.join(list(args) + [f'{k}={v}' for k, v in kwargs.items()])
                                log.info(f'Finished executing function {fn.__name__}({_parameters}) '
                                         f'after {attempt} attempts')
                            else:
                                log.info(f'Finished executing function {fn.__name__}() '
                                         f'after {attempt} attempts')
                        return result
                    except Exception as exc:
                        if non_handling_errors is not None:
                            for _exc_type in non_handling_errors:
                                if isinstance(exc, _exc_type):
                                    raise exc

                        if error_handler:
                            error_handler(exc, Context(fn, *args, **kwargs))

                        if attempt < max_retries:

                            _sleep_time: float = float(min(sleep_time_base ** attempt, sleep_time_max))
                            _jitter = (rnd.randint(-jitter * 1000, jitter * 1000) / 1000) if jitter > 0 else 0
                            _sleep_time = abs(_jitter) if _sleep_time + _jitter < 0 else _sleep_time + _jitter

                            if log.level == logging.DEBUG:
                                _parameters = ', '.join(list(args) + [f'{k}={v}' for k, v in kwargs.items()])
                                log.warning(f'Retry call {fn.__name__}({_parameters}) at {_sleep_time:.03f} seconds. '
                                            f'Reason: {exc.__class__.__qualname__}: {exc}. '
                                            f'Attempt: {attempt}')
                            else:
                                log.warning(f'Retry call {fn.__name__}() at {_sleep_time:.03f} seconds. '
                                            f'Reason: {exc.__class__.__qualname__}: {exc}. '
                                            f'Attempt: {attempt}')
                            time.sleep(_sleep_time)
                        else:
                            raise exc

            return _func()

        return wrapper

    return actual_decorator


def os_open_file(path: str):
    """Cross-platform attempt to open file in associated application."""
    try:
        if os.name == "nt":  # Windows
            os.startfile(path)
        elif sys.platform == "darwin":  # macOS
            subprocess.run(["open", path], check=True)
        elif os.name == "posix":  # Linux and other Unix-like
            subprocess.run(["xdg-open", path], check=True)
        else:
            _log.warning(f"Unsupported OS {os.name} platform {sys.platform}. Unable to open the image outside.")
    except (subprocess.CalledProcessError, OSError) as e:
        _log.warning(f"Error opening image '{path}' in the default image viewer: {e}", exc_info=True)
