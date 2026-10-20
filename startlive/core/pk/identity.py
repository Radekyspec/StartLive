from startlive.core import app_state
from startlive.core.credentials.states import AccountSnapshot
from startlive.core.exceptions import PkAuthenticationError
from startlive.core.pk.states.session import PkIdentity


def current_identity() -> PkIdentity:
    try:
        snapshot = app_state.account_snapshot()
        uid, room_id = snapshot.uid, snapshot.room_id
    except (ValueError, TypeError):
        raise PkAuthenticationError("登录用户或直播间信息无效") from None
    cookies = dict(snapshot.cookies)
    if uid <= 0 or room_id <= 0 or not cookies.get(
            "SESSDATA") or not cookies.get("bili_jct"):
        raise PkAuthenticationError("请先登录并获取直播间信息")
    # QR login supplies cookies, not an OAuth access_key. Never substitute SESSDATA.
    return PkIdentity(uid, room_id, snapshot.cookies, cookies["bili_jct"],
                      buvid=app_state.app_settings.app_buvid)


def require_current_identity(identity: PkIdentity) -> None:
    active = current_identity()
    if not AccountSnapshot(active.uid, active.room_id, active.cookies).matches(
            identity):
        raise PkAuthenticationError("登录账号已改变，请结束当前 PK 后重新开始")
