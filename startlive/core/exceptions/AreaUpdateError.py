class AreaUpdateError(Exception):
    message: str

    def __init__(self, message):
        self.message = message
        super().__init__(f"分区更新时出现错误, 原因: {message}")

    def __repr__(self):
        return f"分区更新时出现错误, 原因: {self.message}"
