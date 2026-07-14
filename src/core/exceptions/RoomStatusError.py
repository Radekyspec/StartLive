class RoomStatusError(Exception):
    message: str

    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return f"当前账号{self.message}, 软件可能无法正常使用"
