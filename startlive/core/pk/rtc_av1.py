"""AV1 Main-profile publishing limits and RTP payloads.

Wire format: https://aomediacodec.github.io/av1-rtp-spec/ (sections 4 and 7).
Level limits: AV1 specification Annex A. Only single-layer, 8-bit 4:2:0
publishing is exposed. Receiving remains negotiated independently as H.264.
"""
from startlive.core.constant.pk_av1 import AV1_LEVELS
from startlive.core.exceptions import PkError, PkProtocolError
from startlive.core.pk.states.av1 import Av1Limits
from startlive.core.pk.states.video import VideoEncodingPlan


def level_limits(level):
    if level not in AV1_LEVELS:
        raise PkProtocolError("不支持的 AV1 level-idx")
    return Av1Limits(level, *AV1_LEVELS[level])


def source_capability():
    # Explicit sender ceiling, exercised by each backend's actual encode probe.
    # This is our capability, not a claim about native LiveHime's SDP.
    return level_limits(9)


def negotiated_limits(offered, parameters):
    def number(key, default, maximum):
        text = str(parameters.get(key, default))
        if not text.isascii() or not text.isdecimal() or int(text) > maximum:
            raise PkProtocolError(f"服务端 AV1 {key} 无效")
        return int(text)

    number("profile", 0, 2)
    number("tier", 0, 1)
    remote = number("level-idx", 5, 31)
    if remote not in AV1_LEVELS and remote != 31:
        raise PkProtocolError("服务端 AV1 level-idx 未定义")
    # Main profile/tier are within a receiver's higher profile/tier capacity.
    return level_limits(min(offered.level, remote))


def encoding_plan(config, limits):
    width, height, fps = config.width, config.height, config.frame_rate
    if (width > limits.max_width or height > limits.max_height
            or width * height > limits.max_pixels
            or width * height * fps > limits.max_pixel_rate):
        raise PkProtocolError("服务端 AV1 能力不足以接收当前固定分辨率和帧率")
    return VideoEncodingPlan(width, height, fps)


def read_leb128(data, offset):
    value = 0
    for shift in range(0, 56, 7):
        if offset >= len(data):
            break
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, offset
    raise PkError("AV1 OBU 长度字段无效")


def split_obus(data):
    """Convert FFmpeg low-overhead OBUs to RTP OBUs without size fields."""
    offset, result = 0, []
    while offset < len(data):
        start = offset
        header = data[offset]
        if header & 0x81 or not header & 2:
            raise PkError("AV1 编码输出不是带长度的 OBU")
        offset += 2 if header & 4 else 1
        size, body = read_leb128(data, offset)
        end = body + size
        if end > len(data):
            raise PkError("AV1 编码输出 OBU 不完整")
        kind = (header >> 3) & 15
        if kind not in (2, 15):  # Temporal delimiters / padding are not sent.
            result.append(
                bytes([header & ~2]) + data[start + 1:offset] + data[body:end])
        offset = end
    return result


def inspect_sequence(obu):
    """Validate the single-operating-point sequence produced by our backend."""
    if not obu or (obu[0] >> 3) & 15 != 1:
        raise PkError("AV1 缺少序列头")
    body = obu[2 if obu[0] & 4 else 1:]
    position = 0

    def bits(count):
        nonlocal position
        if position + count > len(body) * 8:
            raise PkError("AV1 序列头不完整")
        value = 0
        for _ in range(count):
            value = (value << 1) | (
                    (body[position // 8] >> (7 - position % 8)) & 1)
            position += 1
        return value

    profile, still, reduced = bits(3), bits(1), bits(1)
    if profile != 0 or still or reduced or bits(1):  # timing_info_present_flag
        raise PkError("AV1 编码器输出了未配置的序列模式")
    initial_delay = bits(1)
    if bits(5) != 0 or bits(12) != 0:
        raise PkError("AV1 编码器输出了未配置的分层视频")
    level = bits(5)
    tier = bits(1) if level > 7 else 0
    if initial_delay and bits(1):
        bits(4)
    width_bits, height_bits = bits(4) + 1, bits(4) + 1
    return level, tier, bits(width_bits) + 1, bits(height_bits) + 1


def validate_obus(obus, width, height, fps, limits):
    """Validate all sequence headers and return the last one for diagnostics."""
    types = {(obu[0] >> 3) & 15 for obu in obus}
    if not types.intersection((3, 6)):
        raise PkError("AV1 编码输出不包含画面")
    metadata = None
    for obu in obus:
        if (obu[0] >> 3) & 15 == 1:
            metadata = inspect_sequence(obu)
            level, tier, actual_width, actual_height = metadata
            if (level > limits.level or tier != 0
                    or (actual_width, actual_height) != (width, height)):
                raise PkError("AV1 实际序列头超出协商范围或画面尺寸不一致")
            declared = level_limits(level)
            if (width > declared.max_width or height > declared.max_height
                    or width * height > declared.max_pixels
                    or width * height * fps > declared.max_pixel_rate):
                raise PkError("AV1 画面超出码流声明的级别限制")
    return metadata


def packetize(obus):
    """One OBU element per packet (W=1), fragmented to the RTP MTU.

    aiortc marks the last packet of the returned temporal unit and supplies
    one timestamp for the entire unit. N is set only on its sequence start.
    """
    payloads = []
    for obu in obus:
        for offset in range(0, len(obu), 1299):
            end = min(offset + 1299, len(obu))
            header = 0x10 | (0x80 if offset else 0) | (
                0x40 if end < len(obu) else 0)
            if not payloads and (obu[0] >> 3) & 15 == 1:
                header |= 8
            payloads.append(bytes([header]) + obu[offset:end])
    return payloads
