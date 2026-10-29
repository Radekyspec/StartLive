from startlive.core.exceptions import PkAuthenticationError
from startlive.core.identity import current_identity as _current_identity, identity_is_current
from startlive.core.pk.states.session import PkIdentity


def current_identity() -> PkIdentity:
    try:
        return _current_identity()
    except ValueError as error:
        raise PkAuthenticationError(str(error)) from error


def require_current_identity(identity: PkIdentity) -> None:
    if not identity_is_current(identity):
        raise PkAuthenticationError("登录账号已改变，请结束当前 PK 后重新开始")
