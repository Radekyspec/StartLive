class CredentialExpiredError(Exception):
    message: str

    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return f"{self.message}"
