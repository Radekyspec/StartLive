class CredentialExpiredError(Exception):
    message: str

    def __init__(self, message):
        self.message = message
        super().__init__(f"{message}")

    def __repr__(self):
        return f"{self.message}"
