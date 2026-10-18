from startlive.core.exceptions import DanmakuAuthenticationError


def require_current_identity(identity):
    # Import only when a production worker checks its captured account.
    from startlive.core import app_state
    try:
        active = app_state.account_snapshot()
    except (ValueError, TypeError):
        raise DanmakuAuthenticationError("登录用户或直播间信息无效") from None
    if not active.matches(identity):
        raise DanmakuAuthenticationError("登录账号已改变，请重新连接弹幕服务")
