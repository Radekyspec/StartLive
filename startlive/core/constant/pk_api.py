"""Active PK operations: endpoint, native signing rules and diagnostic label."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PkOperation:
    method: str
    path: str
    label: str
    csrf: bool = False
    signed: bool = True
    post_sign_fields: frozenset[str] = frozenset()


# CSRF and trace fields are appended after signing, even for selected GETs.
OPERATIONS = {
    'get_match_select': PkOperation(
        'GET', '/xlive/app-blink/v2/universalInteract/GetMatchSelect',
        '读取连线选项', csrf=True),
    'in_conn_panel': PkOperation(
        'GET', '/xlive/app-blink/v1/universalInteract/InConnPanel',
        '读取连线玩法', csrf=True),
    'batch_recommend_list': PkOperation(
        'GET', '/xlive/app-blink/v2/universalInteract/BatchRecommendList',
        '读取连线候选人', csrf=True),
    'connect': PkOperation(
        'POST', '/xlive/app-blink/v2/universalInteract/Connect', '发起视频连线',
        csrf=True),
    'interact_list': PkOperation(
        'GET', '/xlive/app-blink/v2/universalInteract/InteractList',
        '读取互动列表',
        csrf=True),
    'layout_data': PkOperation(
        'GET', '/xlive/app-blink/v2/universalInteract/LayoutData',
        '读取连线布局',
        csrf=True),
    'match_list': PkOperation(
        'POST', '/xlive/app-blink/v2/universalInteract/MatchList',
        '读取连线匹配列表',
        csrf=True, post_sign_fields=frozenset(('type', 'last_id'))),
    'mute': PkOperation(
        'POST', '/xlive/app-blink/v1/universalInteract/Mute', '同步连线静音',
        csrf=True),
    'user_settings': PkOperation(
        'GET', '/xlive/app-blink/v2/universalInteract/Config', '读取 PK 设置',
        csrf=True),
    'update_user_settings': PkOperation(
        'POST', '/xlive/app-blink/v2/universalInteract/ConfigModify',
        '保存 PK 设置', csrf=True),
    'search_candidates': PkOperation(
        'GET', '/xlive/app-blink/v2/universalInteract/Search', '搜索 PK 用户',
        csrf=True),
    'precheck': PkOperation(
        'GET', '/xlive/general-interface/v1/battle/pkPreCheck', 'PK 预检查',
        post_sign_fields=frozenset(('client_traceid',))),
    'match': PkOperation(
        'GET', '/xlive/general-interface/v1/battle/join', 'PK 匹配',
        post_sign_fields=frozenset(('client_traceid', 'theme_id'))),
    'cancel_match': PkOperation(
        'GET', '/xlive/general-interface/v1/battle/cancel', '取消 PK 匹配',
        post_sign_fields=frozenset(('client_traceid',))),
    'handle': PkOperation(
        'POST', '/xlive/app-blink/v1/universalInteract/Handle', '处理 PK 邀请',
        csrf=True, post_sign_fields=frozenset(('client_traceid',))),
    'handle_room': PkOperation(
        'POST', '/xlive/app-room/v1/universalInteract/Handle', '处理房间邀请',
        csrf=True, post_sign_fields=frozenset(('client_traceid',))),
    'start': PkOperation(
        'POST', '/xlive/general-interface/v2/pk/startMutiPK', '开始 PK',
        csrf=True),
    'exit': PkOperation(
        'POST', '/xlive/general-interface/v2/pk/exit', '退出 PK', csrf=True),
    'info': PkOperation(
        'GET', '/xlive/general-interface/v2/pk/info', '查询 PK 信息',
        csrf=True),
    'classic_info': PkOperation(
        'GET', '/xlive/general-interface/v1/battle/getInfoById',
        '查询经典 PK 信息'),
    'universal_info': PkOperation(
        'GET', '/xlive/app-blink/v2/universalInteract/UniversalInfo',
        '查询连线房间', csrf=True),
    'continuous_status': PkOperation(
        'GET', '/xlive/general-interface/v1/battle/autoMatchSwitchStatus',
        '查询连续 PK 状态', signed=False),
    'continuous_update': PkOperation(
        'GET', '/xlive/general-interface/v1/battle/updateAutoMatchSwitch',
        '更新连续 PK 设置', signed=False),
    'quit': PkOperation(
        'POST', '/xlive/app-blink/v1/universalInteract/Quit', '退出连线',
        csrf=True, post_sign_fields=frozenset(('client_traceid',))),
}

PK_SUCCESS = 0
PK_CLASSIC_INFO_UNAVAILABLE = 6204
