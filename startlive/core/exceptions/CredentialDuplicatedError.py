class CredentialDuplicatedError(Exception):
    message: str

    def __init__(self, message):
        self.message = message
        super().__init__(f"添加了重复的账号凭据: {message}")

    def __repr__(self):
        return f"添加了重复的账号凭据: {self.message}"
