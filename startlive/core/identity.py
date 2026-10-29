from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AccountIdentity:
    uid: int
    room_id: int
    cookies: tuple[tuple[str, str], ...] = field(repr=False)
    csrf: str = field(repr=False)
    access_key: str = field(default="", repr=False)
    buvid: str = field(default="", repr=False)
    generation: int = 0


def current_identity() -> AccountIdentity:
    from startlive.core import app_state

    try:
        generation, _ = app_state.capture_account_context()
        snapshot = app_state.account_snapshot()
        uid, room_id = snapshot.uid, snapshot.room_id
    except (ValueError, TypeError) as error:
        raise ValueError(
            f"登录用户或直播间信息无效：{type(error).__name__}: {error}") from error
    cookies = dict(snapshot.cookies)
    if uid <= 0 or room_id <= 0 or not cookies.get(
            "SESSDATA") or not cookies.get("bili_jct"):
        raise ValueError("请先登录并获取直播间信息")
    # QR login supplies cookies, not an OAuth access_key. Never substitute SESSDATA.
    return AccountIdentity(uid, room_id, snapshot.cookies, cookies["bili_jct"],
                           buvid=app_state.app_settings.app_buvid,
                           generation=generation)


def identity_is_current(identity: AccountIdentity) -> bool:
    from startlive.core import app_state

    return app_state.account_is_current(identity.generation)
