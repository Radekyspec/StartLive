from hashlib import md5
from time import time
from urllib.parse import urlencode

import constant


def livehime_sign(payload, *, access_key: bool = True, build: bool = True,
                  platform: bool = True, ts: bool = True, version: bool = True):
    """
    Sign request payload, not include csrf and csrf_token
    :param payload: raw payload
    :param access_key: whether to include access_key
    :param build: whether to include build
    :param platform: whether to include platform
    :param ts: whether to include ts
    :param version: whether to include version
    """
    signed = base_payload(access_key=access_key, build=build, platform=platform,
                          ts=ts, version=version)
    signed.update({'appkey': constant.APP_KEY})
    signed.update(payload)
    signed = order_payload(signed)  # 按照 key 重排参数
    sign = md5(
        (urlencode(signed, encoding="utf-8") + constant.APP_SECRET).encode(
            encoding="utf-8")).hexdigest()
    signed.update({'sign': sign})
    return signed


def order_payload(payload):
    return dict(sorted(payload.items()))


def base_payload(*, access_key: bool = True, build: bool = True,
                 platform: bool = True, ts: bool = True, version: bool = True):
    res = {}
    if access_key:
        res["access_key"] = ""
    if build:
        res["build"] = constant.LIVEHIME_BUILD
    if platform:
        res["platform"] = "pc_link"
    if ts:
        res["ts"] = str(int(time()))
    if version:
        res["version"] = constant.LIVEHIME_VERSION
    return res

# if __name__ == '__main__':
#     p = {
#     }
#     print(livehime_sign(p))
