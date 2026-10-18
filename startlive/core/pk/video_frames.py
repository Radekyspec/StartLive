"""Owned PyAV frames from tight BGRA/NV12 planes, with source-space crops."""
from av import VideoFrame


def packet_frame(packet, rectangle=None):
    left, top, width, height = rectangle or (0, 0, packet.width, packet.height)
    fmt = packet.pixel_format
    if fmt not in ("bgra", "nv12"):
        raise ValueError("unsupported raw pixel format")
    if (min(left, top) < 0 or min(width,
                                  height) <= 0 or left + width > packet.width
            or top + height > packet.height):
        raise ValueError("out-of-bounds crop")
    if fmt == "nv12" and any(n % 2 for n in
                             (left, top, width, height, packet.width,
                              packet.height)):
        raise ValueError("NV12 crop must be even")
    expected = packet.width * packet.height * (4 if fmt == "bgra" else 3) // (
        1 if fmt == "bgra" else 2)
    if len(packet.payload) != expected:
        raise ValueError("invalid raw video payload")
    frame = VideoFrame(width, height, fmt)
    source = memoryview(packet.payload)
    stride = packet.width * (4 if fmt == "bgra" else 1)
    row_bytes = width * (4 if fmt == "bgra" else 1)
    for index, plane in enumerate(frame.planes):
        rows = height if index == 0 else height // 2
        offset = (top if index == 0 else top // 2) * stride + left * (
            4 if fmt == "bgra" else 1)
        if index:
            offset += packet.width * packet.height
        target = memoryview(plane)
        if stride == row_bytes == plane.line_size:
            target[:rows * row_bytes] = source[offset:offset + rows * row_bytes]
        else:
            for y in range(rows):
                target[
                    y * plane.line_size:y * plane.line_size + row_bytes] = source[
                    offset + y * stride:offset + y * stride + row_bytes]
    frame.colorspace = 5 if packet.colorspace == "ITU601" else 1
    frame.color_range = 1 if packet.color_range == "MPEG" else 2
    return frame


def reformat_packet(reformatter, frame, packet, **kwargs):
    return reformatter.reformat(frame, src_colorspace=packet.colorspace,
                                dst_colorspace=packet.colorspace,
                                src_color_range=packet.color_range, **kwargs)
