class StartLiveError(Exception):
    message: str

    def __init__(self, message):
        self.message = message
        super().__init__(f"尝试开播时返回非正常结果, 原因: {message}")

    def __repr__(self):
        return f"尝试开播时返回非正常结果, 原因: {self.message}"
