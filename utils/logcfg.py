import gzip
import logging.config
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Any

from config import LOGS_DIR, LOG_LEVEL


class InfoFilter(logging.Filter):
    def filter(self, rec):
        return rec.levelno in (logging.DEBUG, logging.INFO)


class ErrorFilter(logging.Filter):
    def filter(self, rec):
        return rec.levelno in (logging.WARNING, logging.ERROR, logging.CRITICAL)


class TimedRotatingFileHandler(RotatingFileHandler):

    def doRollover(self):
        if self.stream:
            self.stream.close()
            # noinspection PyTypeChecker
            self.stream = None

        path = Path(self.baseFilename)
        dfn = str(path.parent / ('%s-%s%s' % (path.stem, time.strftime('%Y%m%d-%H%M%S'), path.suffix)))

        compressed_file_path = f'{dfn}.gz'
        try:
            with open(self.baseFilename, 'rb') as f_in:
                with gzip.open(compressed_file_path, 'wb', compresslevel=9) as f_out:
                    f_out.write(f_in.read())
            os.remove(self.baseFilename)
            logging.debug(f'Compressed log to {compressed_file_path}')
        except PermissionError:
            logging.warning(f'Permission denied: {compressed_file_path}')
        except Exception as e:
            logging.warning(f'Error compressing {compressed_file_path}: {e}')

        if not self.delay:
            self.stream = self._open()


# Logging

class LogType:
    @staticmethod
    def default():
        return {"handlers": ["stdout", "stderr", "file", "err_file"], "level": "INFO", "propagate": False}

    @staticmethod
    def console_only():
        return {"handlers": ["stdout", "stderr"], "level": "DEBUG", "propagate": False}

    @staticmethod
    def warnings_only():
        return {"handlers": ["stderr", "err_file"], "level": "WARNING", "propagate": False}

    @staticmethod
    def errors_only():
        return {"handlers": ["stderr", "err_file"], "level": "ERROR", "propagate": False}


LOGGING_CONFIG: Dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s [%(threadName)s]",
        },
    },
    "filters": {
        "info": {
            "()": InfoFilter,
        },
        "error": {
            "()": ErrorFilter,
        },
    },
    "handlers": {
        "stdout": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "stream": "ext://sys.stdout",
            "filters": ["info"],
        },
        "stderr": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "stream": "ext://sys.stderr",
            "filters": ["error"],
        },
        'file': {
            # 'class': 'logging.FileHandler',
            '()': TimedRotatingFileHandler,
            'maxBytes': 2_560_000,  # 2.56 MB

            'level': 'DEBUG',
            'formatter': 'default',
            'filename': LOGS_DIR / 'app.log',
            'encoding': 'utf-8',
        },
        'err_file': {
            # 'class': 'logging.FileHandler',
            '()': TimedRotatingFileHandler,
            'maxBytes': 2_560_000,  # 2.56 MB

            'level': 'DEBUG',
            'formatter': 'default',
            'filename': LOGS_DIR / 'err.log',
            'encoding': 'utf-8',
            "filters": ["error"],
        },
    },
    "loggers": {
        "root": LogType.default(),
    },
}

LOGGING_LEVELS_TO_DEBUG = {
    1: ['root'],
}


def apply():
    for level, logger_names in LOGGING_LEVELS_TO_DEBUG.items():
        if LOG_LEVEL >= level:
            for name in logger_names:
                LOGGING_CONFIG['loggers'][name]['level'] = 'DEBUG'

    logging.config.dictConfig(LOGGING_CONFIG)
