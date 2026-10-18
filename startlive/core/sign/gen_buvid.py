import os
from uuid import uuid4


def gen_buvid():
    return f"{str(uuid4()).upper()}{os.getpid()}user"
