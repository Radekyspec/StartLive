"""Contract21 common PK_INFO projection and normal code0 classic conversion."""
from copy import deepcopy
from dataclasses import replace
from math import isfinite

from startlive.core.constant.pk_api import PK_SUCCESS, \
    PK_CLASSIC_INFO_UNAVAILABLE
from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.states.info import (
    PkBasicInfo,
    PkClassicInfoResult,
    PkInfo,
    PkMatchInfo,
    PkMemberInfo,
)


def _number(data, key, *, bits=64):
    value = data.get(key, 0)
    if isinstance(value, str) and value.isascii() and value.removeprefix(
            "-").isdecimal():
        value = int(value)
    if type(value) is not int or not -(1 << (bits - 1)) <= value < 1 << (
            bits - 1):
        raise PkProtocolError("PK 状态的数值格式无效")
    return value


def _text(data, key):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise PkProtocolError("PK 状态的文本格式无效")
    return value


def _optional_number(data, key, *, bits=64):
    if key not in data:
        return None
    value = data[key]
    # Native member DTOs also accept finite doubles and truncate them.
    if type(value) is float and isfinite(value):
        value = int(value)
    try:
        return _number({key: value}, key, bits=bits)
    except PkProtocolError:
        return None


def _member(data, *, classic=False):
    votes = _optional_number(data, "votes")
    winner = (_optional_number(data, "winner_type", bits=32) if classic else
              _optional_number(data, "is_winner", bits=32))
    winner = {1: 2, 2: 1, 3: 1}.get(
        winner) if classic else winner if winner in (0, 1, 2) else None
    return PkMemberInfo(uid=_optional_number(data, "uid") or 0,
                        room_id=_optional_number(data, "room_id") or 0,
                        votes=votes,
                        votes_text=str(
                            votes) if classic and votes is not None else
                        "" if classic else _text(data, "votes_text"),
                        uname=_text(data, "uname"), face=_text(data, "face"),
                        is_winner=winner)


def _countdown(status, timestamp, end, punish_end):
    endpoint = end if status == 201 else punish_end if status in (601, 602,
                                                                  610) else None
    return max(0,
               endpoint - timestamp) if timestamp is not None and endpoint is not None else None


def parse_pk_info(data):
    if not isinstance(data, dict) or not isinstance(data.get("pk_basic"), dict):
        raise PkProtocolError("PK_INFO 缺少回合信息")
    basic = data["pk_basic"]
    match = data.get("pk_match_info", {})
    if match is None:
        # Active-round pushes may explicitly omit optional matching metadata.
        # Keep the same defaults as an absent section; raw retains the null.
        match = {}
    if not isinstance(match, dict):
        raise PkProtocolError("PK_INFO 匹配信息无效")
    numbers = {name: _number(basic, name) for name in (
        "pk_id", "init_id", "status", "type", "sub_type", "start_time",
        "end_time",
        "punish_end_time", "sprint_duration", "muti_pk_type")}
    texts = {name: _text(basic, name) for name in
             ("biz_session_id", "punish_text", "status_msg")}
    members = data.get("members", [])
    if members is None:
        # Matching responses have no opponent yet and explicitly return null.
        # Match an absent list without changing the original response in raw.
        members = []
    if not isinstance(members, list):
        raise PkProtocolError("PK 成员信息格式无效")
    return PkInfo(4, PkBasicInfo(**numbers, **texts),
                  PkMatchInfo(_number(match, "match_status", bits=32),
                              _number(match, "match_max_time"),
                              _number(match, "match_end_time")),
                  _number(data, "timestamp"), deepcopy(data),
                  members=tuple(_member(member) for member in members if
                                isinstance(member, dict)),
                  countdown_seconds=_countdown(numbers["status"],
                                               _optional_number(data,
                                                                "timestamp"),
                                               _optional_number(basic,
                                                                "end_time"),
                                               _optional_number(basic,
                                                                "punish_end_time")))


def classic_info_result(code, data):
    """Contract44 keeps the classic callback code and separate auto status."""
    if code not in (PK_SUCCESS, PK_CLASSIC_INFO_UNAVAILABLE) or not isinstance(
            data, dict):
        raise PkProtocolError("经典 PK 查询缺少有效的状态响应")
    return PkClassicInfoResult(code,
                               _number(data, "auto_match_status", bits=32),
                               deepcopy(data))


def classic_pk_info(data, *, auto_matching=False, cached_timestamp=0):
    """Convert actual fields; auto_matching requires Contract44's6204 gate."""
    if not isinstance(data, dict):
        raise PkProtocolError("经典 PK 查询缺少状态信息")
    timestamp = _number(data, "timestamp")
    if auto_matching:
        timestamp = timestamp or cached_timestamp + 1
    end = _optional_number(data, "pk_frozen_time")
    sprint_start = _optional_number(data, "pk_countdown")
    punishment = data.get("video_punish")
    duration = _optional_number(punishment, "duration") if isinstance(
        punishment, dict) else None
    punish_end = timestamp + duration if duration is not None else None
    info = PkInfo(3, PkBasicInfo(pk_id=_number(data, "pk_id"),
                                 status=_number(data, "status", bits=32),
                                 type=_number(data, "battle_type", bits=32),
                                 sub_type=_number(data, "battle_sub_type",
                                                  bits=32), muti_pk_type=-1,
                                 start_time=_number(data, "pk_start_time"),
                                 end_time=end or 0,
                                 sprint_duration=end - sprint_start if end is not None and sprint_start is not None else 0,
                                 punish_end_time=punish_end or 0,
                                 punish_text=_text(data, "punish_name")),
                  PkMatchInfo(_number(data, "match_status", bits=32),
                              _number(data, "match_max_time", bits=32),
                              _number(data, "match_end_time")),
                  timestamp, deepcopy(data), legacy=True,
                  members=tuple(_member(data[key], classic=True) for key in
                                ("init_info", "match_info")
                                if isinstance(data.get(key), dict)),
                  countdown_seconds=None if auto_matching else _countdown(
                      _number(data, "status", bits=32),
                      _optional_number(data, "timestamp"), end, punish_end))
    if auto_matching:
        info = replace(info, basic=replace(info.basic, status=0),
                       match=replace(info.match, match_status=1),
                       timestamp=timestamp)
    return info


def queried_pk_info(data):
    """Contract27 code0 v2/pk/info uses the nested common DTO, source3."""
    return replace(parse_pk_info(data), source_kind=3)
