from logging import DEBUG
from logging import Logger, LoggerAdapter
from logging import getLogger
from logging.handlers import TimedRotatingFileHandler

from constant import LOGGER_NAME, CacheType
from models.cache import get_cache_path
from .formatter import ThreadClassFormatter
from .handler import QSignalLogHandler


def get_log_path(*, is_makedir: bool = True) -> tuple[str, str]:
    return get_cache_path(CacheType.LOGS, "StartLive.log",
                          is_makedir=is_makedir)


def init_logger(name: str = LOGGER_NAME) -> tuple[Logger, QSignalLogHandler]:
    logger = getLogger(name)
    logger.setLevel(DEBUG)
    log_dir, log_path = get_log_path()
    fh = TimedRotatingFileHandler(
        log_path, when="midnight", interval=1, backupCount=14, encoding="utf-8"
    )
    gui_handler = QSignalLogHandler()
    fh.suffix = "%Y-%m-%d.log"
    fh.namer = lambda _name: _name.replace(".log.", ".")
    tc_formatter = ThreadClassFormatter(
        "%(asctime)s.%(msecs)03d [%(threadClassName)s] - %(message)s",
        "%Y-%m-%d %H:%M:%S")
    fh.setFormatter(tc_formatter)
    gui_handler.setFormatter(tc_formatter)
    logger.addHandler(fh)
    logger.addHandler(gui_handler)

    # ch = StreamHandler()
    # ch.setFormatter(formatter)
    # logger.addHandler(ch)
    return logger, gui_handler


def get_logger(thread_name: str, name: str = LOGGER_NAME) -> LoggerAdapter:
    logger = getLogger(name)
    adapter = LoggerAdapter(logger, {"threadClassName": thread_name})
    return adapter
