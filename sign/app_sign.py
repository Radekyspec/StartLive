from hashlib import md5
from time import time
from urllib.parse import urlencode

APP_KEY = "aae92bc66f3edfab"
APP_SECRET = "af125a0d5279fd576c1b4418a3e8276d"
LIVEHIME_BUILD = "8931"


def livehime_sign(payload):
    """
    Sign request payload, not include csrf and csrf_token
    Demo modified from https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign/APP.md
    Thanks for the community!
    :param payload: original request payload
    :return: signed payload
    """
    signed = base_payload()
    signed.update({'appkey': APP_KEY})
    signed.update(payload)
    signed = order_payload(signed)  # 按照 key 重排参数
    sign = md5((urlencode(signed) + APP_SECRET).encode()).hexdigest()
    signed.update({'sign': sign})
    return signed


def order_payload(payload):
    return dict(sorted(payload.items()))


def base_payload():
    return {
        "access_key": "",
        "build": "8931",
        "platform": "pc_link",
        "ts": str(int(time())),
        "version": "7.11.3.8931",
    }


if __name__ == '__main__':
    params = {
        "access_key": "",
        "area_v2": "371",
        "build": "8931",
        # "csrf": "1bc852ba5a77631f5ca40e178f319413",
        # "csrf_token": "1bc852ba5a77631f5ca40e178f319413",
        "platform": "pc_link",
        "room_id": "22593055",
        "ts": "1748027349",
        "type": "2",
        "version": "7.11.3.8931",
    }
    print(livehime_sign(params))
