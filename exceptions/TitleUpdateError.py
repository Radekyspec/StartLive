class TitleUpdateError(Exception):
    message: str

    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return f"标题更新时出现错误, 原因: {self.message}"
