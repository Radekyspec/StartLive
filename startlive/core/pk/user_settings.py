"""Contract51 full Config snapshots and the ten requested preference changes."""
from dataclasses import replace

from startlive.core.constant.pk_user_settings import PK_SETTING_SWITCH_FIELDS
from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.states.preferences import PkPreferenceValues
from startlive.core.pk.states.user_settings import PkUserSettingsSnapshot


def _integer(value, *, bits=32):
    if type(value) is not int or not -(1 << (bits - 1)) <= value < 1 << (
            bits - 1):
        raise PkProtocolError("PK 设置缺少有效的整数值")
    return value


def _options(data, field):
    values = data.get(field)
    if not isinstance(values, dict) or not values:
        raise PkProtocolError("PK 设置缺少有效的时长选项")
    options, selected = [], []
    for key, marker in values.items():
        if not isinstance(key,
                          str) or not key.isascii() or not key.removeprefix(
            "-").isdecimal():
            # Native Config parser skips non-numeric object keys; they are not
            # duration choices. A valid selected numeric option is still required.
            continue
        option = _integer(int(key), bits=64)
        if option in options:
            raise PkProtocolError("PK 设置的时长选项重复")
        options.append(option)
        if _integer(marker) == 1:
            selected.append(option)
    if len(selected) != 1:
        raise PkProtocolError("尚未确认 PK 设置当前选择的时长")
    return tuple(options), selected[0]


def parse_user_settings(data) -> PkUserSettingsSnapshot:
    if not isinstance(data, dict):
        raise PkProtocolError("PK 设置响应无效")
    switches = {}
    for semantic, wire in PK_SETTING_SWITCH_FIELDS.items():
        value = _integer(data.get(wire))
        if value not in (0, 1):
            raise PkProtocolError("PK 设置的开关值暂不支持")
        switches[semantic] = value == 1
    duration_options, duration = _options(data, "pk_time_list")
    # LiveHime 8.7.0.11081 initializes Config DTO +0x70 to zero; null skips
    # option parsing, and full ConfigModify still sends pk_punish_time="0".
    # This is client compatibility, not a claim about server-side zero semantics.
    # Evidence: contracts/51-settings-null-punish-save.json.
    if "pk_punish_time_list" in data and data["pk_punish_time_list"] is None:
        punish_options, punish_time = (), 0
    else:
        punish_options, punish_time = _options(data, "pk_punish_time_list")
    return PkUserSettingsSnapshot(PkPreferenceValues(duration, **switches),
                                  duration_options,
                                  _integer(data.get("show_score")), punish_time,
                                  punish_options)


def build_settings_change(snapshot: PkUserSettingsSnapshot, field: str,
                          value) -> PkUserSettingsSnapshot:
    """Apply an explicit user intent to a complete confirmed snapshot only.

    Couplings are native control behavior; these preferences do not start PK,
    accept an invitation, change outgoing duration fields or mute media.
    """
    if not isinstance(snapshot, PkUserSettingsSnapshot):
        raise PkProtocolError("请先读取当前账号的完整 PK 设置")
    preferences = snapshot.preferences
    if field == "duration":
        if type(value) is not int or value not in snapshot.duration_options:
            raise PkProtocolError("请选择服务端提供的 PK 时长")
    elif field not in PK_SETTING_SWITCH_FIELDS or type(value) is not bool:
        raise PkProtocolError("PK 设置修改项或值无效")
    changes = {field: value}
    if field == "accept_pk":
        changes["accept_unfollowed_pk"] = value
    elif field == "accept_unfollowed_pk" and value:
        changes["accept_pk"] = True
    elif field == "accept_connection":
        changes["mutual_only"] = value and preferences.mutual_only
    elif field == "mutual_only" and value:
        changes["accept_connection"] = True
    elif field == "allow_apply_join":
        changes["allow_auto_join"] = value and preferences.allow_auto_join
    elif field == "allow_auto_join" and value:
        changes["allow_apply_join"] = True
    return replace(snapshot, preferences=replace(preferences, **changes))
