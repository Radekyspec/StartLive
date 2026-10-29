"""Active PK operations: endpoint, native signing rules and diagnostic label."""
# CSRF and trace fields are appended after signing, even for selected GETs.
OPERATIONS = {
    'get_match_select': dict(
        method='GET', path='/xlive/app-blink/v2/universalInteract/GetMatchSelect',
        label='读取连线选项', csrf=True),
    'in_conn_panel': dict(
        method='GET', path='/xlive/app-blink/v1/universalInteract/InConnPanel',
        label='读取连线玩法', csrf=True),
    'batch_recommend_list': dict(
        method='GET', path='/xlive/app-blink/v2/universalInteract/BatchRecommendList',
        label='读取连线候选人', csrf=True),
    'connect': dict(
        method='POST', path='/xlive/app-blink/v2/universalInteract/Connect',
        label='发起视频连线',
        csrf=True),
    'interact_list': dict(
        method='GET', path='/xlive/app-blink/v2/universalInteract/InteractList',
        label='读取互动列表',
        csrf=True),
    'layout_data': dict(
        method='GET', path='/xlive/app-blink/v2/universalInteract/LayoutData',
        label='读取连线布局',
        csrf=True),
    'match_list': dict(
        method='POST', path='/xlive/app-blink/v2/universalInteract/MatchList',
        label='读取连线匹配列表',
        csrf=True, post_sign_fields=frozenset(('type', 'last_id'))),
    'mute': dict(
        method='POST', path='/xlive/app-blink/v1/universalInteract/Mute',
        label='同步连线静音',
        csrf=True),
    'user_settings': dict(
        method='GET', path='/xlive/app-blink/v2/universalInteract/Config',
        label='读取 PK 设置',
        csrf=True),
    'update_user_settings': dict(
        method='POST', path='/xlive/app-blink/v2/universalInteract/ConfigModify',
        label='保存 PK 设置', csrf=True),
    'search_candidates': dict(
        method='GET', path='/xlive/app-blink/v2/universalInteract/Search',
        label='搜索 PK 用户',
        csrf=True),
    'precheck': dict(
        method='GET', path='/xlive/general-interface/v1/battle/pkPreCheck',
        label='PK 预检查',
        post_sign_fields=frozenset(('client_traceid',))),
    'match': dict(
        method='GET', path='/xlive/general-interface/v1/battle/join',
        label='PK 匹配',
        post_sign_fields=frozenset(('client_traceid', 'theme_id'))),
    'cancel_match': dict(
        method='GET', path='/xlive/general-interface/v1/battle/cancel',
        label='取消 PK 匹配',
        post_sign_fields=frozenset(('client_traceid',))),
    'handle': dict(
        method='POST', path='/xlive/app-blink/v1/universalInteract/Handle',
        label='处理 PK 邀请',
        csrf=True, post_sign_fields=frozenset(('client_traceid',))),
    'handle_room': dict(
        method='POST', path='/xlive/app-room/v1/universalInteract/Handle',
        label='处理房间邀请',
        csrf=True, post_sign_fields=frozenset(('client_traceid',))),
    'start': dict(
        method='POST', path='/xlive/general-interface/v2/pk/startMutiPK',
        label='开始 PK',
        csrf=True),
    'exit': dict(
        method='POST', path='/xlive/general-interface/v2/pk/exit',
        label='退出 PK', csrf=True),
    'info': dict(
        method='GET', path='/xlive/general-interface/v2/pk/info',
        label='查询 PK 信息',
        csrf=True),
    'classic_info': dict(
        method='GET', path='/xlive/general-interface/v1/battle/getInfoById',
        label='查询经典 PK 信息'),
    'universal_info': dict(
        method='GET', path='/xlive/app-blink/v2/universalInteract/UniversalInfo',
        label='查询连线房间', csrf=True),
    'continuous_status': dict(
        method='GET', path='/xlive/general-interface/v1/battle/autoMatchSwitchStatus',
        label='查询连续 PK 状态', signed=False),
    'continuous_update': dict(
        method='GET', path='/xlive/general-interface/v1/battle/updateAutoMatchSwitch',
        label='更新连续 PK 设置', signed=False),
    'quit': dict(
        method='POST', path='/xlive/app-blink/v1/universalInteract/Quit',
        label='退出连线',
        csrf=True, post_sign_fields=frozenset(('client_traceid',))),
}

PK_SUCCESS = 0
PK_CLASSIC_INFO_UNAVAILABLE = 6204
