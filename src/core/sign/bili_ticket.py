import hashlib
import hmac


def ticket_hmac_sha256(timestamp: int) -> str:
    # 将密钥和消息转换为字节串
    key = "XgwSnGZ1p".encode('utf-8')
    message = f"ts{timestamp}".encode('utf-8')

    # 创建HMAC对象，使用SHA256哈希算法
    hmac_obj = hmac.new(key, message, hashlib.sha256)

    # 计算哈希值
    hash_value = hmac_obj.digest()

    # 将哈希值转换为十六进制字符串
    hash_hex = hash_value.hex()

    return hash_hex
