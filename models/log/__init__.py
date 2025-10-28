import os
from logging import DEBUG
from logging import Logger, LoggerAdapter
from logging import getLogger
from logging.handlers import TimedRotatingFileHandler
from platform import system

from constant import LOGGER_NAME
from .formatter import ThreadClassFormatter
from .handler import QSignalLogHandler


def get_log_path(*, is_makedir: bool = True) -> tuple[str, str]:
    if (_arch := system()) == "Windows":
        try:
            base_dir = os.path.abspath(__compiled__.containing_dir)
        except NameError:
            base_dir = os.path.abspath(".")
        base_dir = os.path.join(base_dir, "logs")
        log_path = os.path.join(base_dir, "StartLive.log")
    elif _arch == "Linux":
        base_dir = os.path.join(os.path.expanduser("~"), ".cache", "StartLive",
                                "logs")
        log_path = os.path.join(base_dir, "StartLive.log")
    elif _arch == "Darwin":
        base_dir = os.path.join(os.path.expanduser("~"), "Library", "Logs",
                                "StartLive")
        log_path = os.path.join(base_dir, "StartLive.log")
    else:
        raise ValueError("Unsupported system")
    if is_makedir:
        os.makedirs(base_dir, exist_ok=True)
    return base_dir, log_path


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
