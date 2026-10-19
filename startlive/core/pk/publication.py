"""Modern JOIN publication source, independent of config.enable_* flags."""
from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.states.publication import PkPublishChannels


def publication_channels(join_event):
    control = join_event.stream_control.get("pub_sub_control", {})
    if not isinstance(control, dict):
        raise PkProtocolError("JOIN 发布控制格式无效")
    # Native stream-control constructor defaults to audio-only. Unknown
    # numeric modes are blocked by StartLive instead of enabling extra tracks.
    status = control.get("pub_status", 1)
    if type(status) is not int or status not in (0, 1, 2, 3):
        raise PkProtocolError("JOIN 发布模式尚不受支持")
    return PkPublishChannels(video=status in (2, 3), audio=status in (1, 3))
