class TitleStatusError(Exception):
    message: str

    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return f"标题状态异常: {self.message}"
