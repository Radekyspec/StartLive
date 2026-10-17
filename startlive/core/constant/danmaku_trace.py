"""Danmaku diagnostic labels."""

_DESCRIPTIONS = {
    "http.response": "弹幕连接请求响应 Response",
    "http.parsed": "弹幕连接响应解析 Result",
    "http.error": "弹幕连接请求或解析失败",
    "connection.state": "弹幕连接状态更新",
    "connection.reconnect": "弹幕连接中断，准备重连",
    "connection.failed": "弹幕连接或报文处理失败",
    "push.receive.failed": "弹幕推送解析或处理失败",
    "push.sequence_ack.failed": "弹幕推送序列确认失败",
    "push.auth.response": "弹幕推送鉴权响应",
}
