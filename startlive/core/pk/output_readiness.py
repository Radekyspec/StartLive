"""StartLive output facts. These are local equivalents, not LiveHime provider flags."""
from time import monotonic

from startlive.core.constant.pk import PkMode
from startlive.core.exceptions import PkError
from startlive.core.pk.states.output import PkOutputReadiness


def output_readiness(status, mode, *, now=None, status_max_age=3):
    """Business admission uses live output, not the optional RTC capture bridge."""
    now = monotonic() if now is None else now
    if status.active is None or not 0 <= now - status.observed_at <= status_max_age:
        return PkOutputReadiness(None, None, None, "尚未取得 OBS 当前推流状态")
    live = status.active is True and status.reconnecting is False
    if not live:
        return PkOutputReadiness(False, False, None, "OBS 尚未推流或正在重连")
    if mode == PkMode.TRADITIONAL:
        # Traditional PK uses the existing broadcast. StartLive has no separate
        # LiveHime voice-microphone service to initialize or invent a flag for.
        return PkOutputReadiness(True, True, True, "OBS 正在推流（经典 PK）")
    # StartLive has no voice-microphone service conflict to gate here. Capture
    # availability is checked separately against the JOIN publication selection.
    return PkOutputReadiness(True, True, True, "OBS 正在推流",
                             source="OBS GetStreamStatus")


def require_publication_capture(media_buffer, *, video, audio, now=None,
                                max_age=2):
    """Local freshness policy for selected send tracks, never server eligibility."""
    if not video and not audio:
        return
    fresh_video, fresh_audio = media_buffer.freshness(now=now, max_age=max_age)
    missing = [name for name, enabled, fresh in (
        ("画面", video, fresh_video), ("声音", audio, fresh_audio)) if
               enabled and not fresh]
    if missing:
        raise PkError("OBS 发布采集尚未就绪：缺少新鲜的" + "和".join(missing))
