class LoginError(Exception):
    message: str

    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return f"登录时出现错误, 原因: {self.message}"
