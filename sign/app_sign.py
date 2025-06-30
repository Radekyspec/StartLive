from hashlib import md5
from time import time
from urllib.parse import urlencode

import constant
# from constant import APP_KEY, APP_SECRET, LIVEHIME_BUILD, LIVEHIME_VERSION


def livehime_sign(payload):
    """
    Sign request payload, not include csrf and csrf_token
    :param payload:
    """
    signed = base_payload()
    signed.update({'appkey': constant.APP_KEY})
    signed.update(payload)
    signed = order_payload(signed)  # 按照 key 重排参数
    sign = md5((urlencode(signed, encoding="utf-8") + constant.APP_SECRET).encode(
        encoding="utf-8")).hexdigest()
    signed.update({'sign': sign})
    return signed


def order_payload(payload):
    return dict(sorted(payload.items()))


def base_payload():
    return {
        "access_key": "",
        "build": constant.LIVEHIME_BUILD,
        "platform": "pc_link",
        "ts": str(int(time())),
        # "ts": "1751267234",
        "version": constant.LIVEHIME_VERSION,
    }


# if __name__ == '__main__':
#     p = {
#         # "csrf": "f835293f3568ddb4093aa8299f5e6c0b",
#         # "csrf_token": "f835293f3568ddb4093aa8299f5e6c0b",
#         "room_id": 22593055,
#     }
#     print(livehime_sign(p))
