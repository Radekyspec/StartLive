class RoomStatusError(Exception):
    message: str

    def __init__(self, message):
        self.message = message
        super().__init__(f"当前账号{message}, 软件可能无法正常使用")

    def __repr__(self):
        return f"当前账号{self.message}, 软件可能无法正常使用"
