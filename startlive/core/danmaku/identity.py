from startlive.core.exceptions import DanmakuAuthenticationError
from startlive.core.identity import identity_is_current


def require_current_identity(identity):
    if not identity_is_current(identity):
        raise DanmakuAuthenticationError("登录账号已改变，请重新连接弹幕服务")
