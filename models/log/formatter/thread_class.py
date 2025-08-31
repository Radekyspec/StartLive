from logging import Formatter


class ThreadClassFormatter(Formatter):
    def format(self, record) -> str:
        record.threadClassName = getattr(record, 'threadClassName', 'N/A')
        return super().format(record)