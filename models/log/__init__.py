import os
from logging import DEBUG
from logging import Formatter, Logger, LoggerAdapter, StreamHandler
from logging import getLogger
from logging.handlers import TimedRotatingFileHandler
from platform import system

from constant import LOGGER_NAME


class ThreadClassFormatter(Formatter):
    def format(self, record) -> str:
        record.threadClassName = getattr(record, 'threadClassName', 'N/A')
        return super().format(record)


def init_logger(name: str = LOGGER_NAME) -> Logger:
    logger = getLogger(name)
    logger.setLevel(DEBUG)
    if system() == "Windows":
        try:
            base_dir = os.path.abspath(__compiled__.containing_dir)
        except NameError:
            base_dir = os.path.abspath(".")
        os.makedirs(os.path.join(base_dir, "logs"), exist_ok=True)
        log_dir = os.path.join(base_dir, "logs")
        log_path = os.path.join(log_dir, "StartLive.log")
    elif system() == "Linux":
        base_dir = os.path.join("var", "log", "StartLive")
        os.makedirs(base_dir, exist_ok=True)
        log_dir = base_dir
        log_path = os.path.join(log_dir, "StartLive.log")
    elif system() == "Darwin":
        base_dir = os.path.join(os.path.expanduser("~"), "Library", "Logs", "StartLive")
        os.makedirs(base_dir, exist_ok=True)
        log_dir = base_dir
        log_path = os.path.join(log_dir, "StartLive.log")
    else:
        raise ValueError("Unsupported system")
    fh = TimedRotatingFileHandler(
        log_path, when="midnight", interval=1, backupCount=0, encoding="utf-8"
    )
    fh.suffix = "%Y-%m-%d.log"
    fh.extMatch = fh.extMatch
    fh.namer = lambda name: name.replace(".log.", ".")
    formatter = ThreadClassFormatter(
        "%(asctime)s [%(threadClassName)s] - %(message)s",
        "%Y-%m-%d %H:%M:%S")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # ch = StreamHandler()
    # ch.setFormatter(formatter)
    # logger.addHandler(ch)
    return logger

def get_logger(thread_name: str, name: str = LOGGER_NAME) -> LoggerAdapter:
    logger = getLogger(name)
    adapter = LoggerAdapter(logger, {"threadClassName": thread_name})
    return adapter
