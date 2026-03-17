class CredentialDuplicatedError(Exception):
    message: str

    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return f"添加了重复的账号凭据: {self.message}"
