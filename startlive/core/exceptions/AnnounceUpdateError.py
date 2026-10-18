class AnnounceUpdateError(Exception):
    message: str

    def __init__(self, message):
        self.message = message
        super().__init__(f"主播公告更新时出现错误, {message}")

    def __repr__(self):
        return f"主播公告更新时出现错误, {self.message}"
