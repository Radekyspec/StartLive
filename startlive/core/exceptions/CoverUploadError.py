class CoverUploadError(Exception):
    message: str

    def __init__(self, message):
        self.message = message
        super().__init__(f"上传封面时出现错误, 原因: {message}")

    def __repr__(self):
        return f"上传封面时出现错误, 原因: {self.message}"
