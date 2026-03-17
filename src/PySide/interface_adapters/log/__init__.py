from logging import Logger

from src.core.constant import LOGGER_NAME
from src.core.log import ThreadClassFormatter
from src.core.log import init_logger as init_core_logger
from .handler import QSignalLogHandler


def init_logger(name: str = LOGGER_NAME) -> tuple[Logger, QSignalLogHandler]:
    logger = init_core_logger(name)
    gui_handler = QSignalLogHandler()
    tc_formatter = ThreadClassFormatter(
        "%(asctime)s.%(msecs)03d [%(threadClassName)s] - %(message)s",
        "%Y-%m-%d %H:%M:%S")
    gui_handler.setFormatter(tc_formatter)
    logger.addHandler(gui_handler)
    return logger, gui_handler
