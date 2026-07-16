from math import floor
from random import random

from src.core.app_state import dumps


def gen_dm_track(wh: tuple[int, int] = (500, 420),
                 center: tuple[int, int] = (0, 0)) -> str:
    """
    Generate dm_track from bili-user-fingerprint.min.js
    :param wh: window width and height
    :param center: window center position
    :return: {dm_img_list, dm_img_str, dm_cover_img_str, dm_img_inter}

    dm_img_list: 用户行为事件日志，例如鼠标、键盘、触摸、focus

    dm_img_str: WebGL version 字符串编码

    dm_cover_img_str: WebGL vendor + renderer 字符串编码

    dm_img_inter: [ds, wh, of] 当前页面元素、窗口大小、滚动位置等信息

    Base64 输出并固定删掉最后两个字符
    """
    return dumps({
        "dm_img_list": [],  # fine to be empty
        "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
        "dm_cover_img_str": "QU5HTEUgKEludGVsLCBJbnRlbChSKSBVSEQgR3JhcGhpY3MgRGlyZWN0M0QxMSB2c181XzAgcHNfNV8wLCBEM0QxMSlHb29nbGUgSW5jLiAoSW50ZW",
        "dm_img_inter": dumps({
            "ds": [],
            "wh": list(_gen_wh(wh)),
            "of": list(_gen_of(center))
        })
    })


def _gen_wh(wh: tuple[int, int]):
    a, b = wh
    r = floor(114 * random())
    return 2 * a + 2 * b + 3 * r, 4 * a - b + r, r


def _gen_of(center: tuple[int, int]):
    a, b = center
    r = floor(514 * random())
    return 3 * a + 2 * b + r, 4 * a - 4 * b + 2 * r, r
