class WorkerException(Exception):
    name: str
    real_exc: Exception

    def __init__(self, name, real_exc):
        self.name = name
        self.real_exc = real_exc

    def __repr__(self):
        return f"{self.name}线程错误: {self.real_exc}"
