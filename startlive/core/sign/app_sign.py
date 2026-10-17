from collections.abc import Mapping
from hashlib import md5
from time import time
from urllib.parse import quote, urlencode

from startlive.core import constant


def encode_payload(payload, *, native_wire: bool = False) -> str:
    """Encode an ordered mapping or ordered pairs, preserving repeated keys.

    The standard Livehime signer uses ``urlencode`` defaults. Native PK and
    danmaku requests instead preserve !'()*~ and encode spaces as %20.
    """
    if native_wire:
        # JSON fixtures (and some callers) supply ordered pairs as lists;
        # urllib.urlencode requires tuples for sequence-of-pairs input.
        pairs = [tuple(pair) for pair in
                 (payload.items() if isinstance(payload, Mapping) else payload)]
        if any(not isinstance(key, str) or not isinstance(value, str)
               for key, value in pairs):
            raise TypeError("Native wire parameters must be explicit strings")
        return urlencode(pairs, encoding="utf-8", errors="strict",
                         quote_via=quote, safe="!'()*-._~")
    return urlencode(payload, encoding="utf-8")


def native_canonical(payload) -> str:
    """Sorted native pc_link wire parameters, prior to adding a signature."""
    return encode_payload(order_payload(payload), native_wire=True)


def sign_preimage(preimage: str) -> str:
    """Apply the shared Livehime app secret to an already encoded preimage."""
    return md5((preimage + constant.APP_SECRET).encode("utf-8")).hexdigest()


def livehime_sign(payload, *, access_key: bool = True, build: bool = True,
                  platform: bool = True, ts: bool = True, version: bool = True,
                  native_wire: bool = False):
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
    sign = sign_preimage(encode_payload(signed, native_wire=native_wire))
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


if __name__ == '__main__':
    import itertools


    def get_all_subsets_with_itertools(data_list):
        """
        使用 `itertools.combinations` 获取列表的所有子集。

        Args:
            data_list: 输入的列表。

        Returns:
            一个包含所有子集的列表。
        """
        all_subsets = []
        for i in range(len(data_list) + 1):
            for subset in itertools.combinations(data_list, i):
                all_subsets.append(list(subset))
        return all_subsets


    p = {
    }
    print(livehime_sign(p)["sign"])
    for i in get_all_subsets_with_itertools(p.keys()):
        j = {}
        for k in i:
            j[k] = p[k]
        print(j)
        print(livehime_sign(j)["sign"])
