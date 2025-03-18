import logging


class Logged:
    def __init__(self, log_tag: str | None = None, logger_name: str | None = None):
        self.__logger: logging.Logger = logging.getLogger(logger_name if logger_name else self.__class__.__qualname__)
        self.__log_tag: str = f'[{log_tag}] ' if log_tag else ''
        self.____log_tag = log_tag

    @property
    def log_tag(self):
        return self.____log_tag

    @log_tag.setter
    def log_tag(self, value):
        self.____log_tag = value
        self.__log_tag = f'[{value}] ' if value else ''

    def __log(self, level: int, msg: object, *args, exc_info=None, **kwargs):
        self.__logger.log(level, f'{self.__log_tag}{msg}'.replace('\n', '\\n'), *args, exc_info=exc_info, **kwargs)

    def debug(self, msg: object, *args, exc_info=None, **kwargs):
        self.__log(logging.DEBUG, msg, *args, exc_info=exc_info, **kwargs)

    def info(self, msg: object, *args, exc_info=None, **kwargs):
        self.__log(logging.INFO, msg, *args, exc_info=exc_info, **kwargs)

    def warning(self, msg: object, *args, exc_info=None, **kwargs):
        self.__log(logging.WARNING, msg, *args, exc_info=exc_info, **kwargs)

    def error(self, msg: object, *args, exc_info=None, **kwargs):
        self.__log(logging.ERROR, msg, *args, exc_info=exc_info, **kwargs)

    def critical(self, msg: object, *args, exc_info=None, **kwargs):
        self.__log(logging.CRITICAL, msg, *args, exc_info=exc_info, **kwargs)
