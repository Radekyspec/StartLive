import os
from base64 import b64decode, b64encode
from hashlib import sha256
from json import loads
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from src.core.app_state import dumps

MASK64 = 0xFFFFFFFFFFFFFFFF


def _rotl64(x: int, r: int) -> int:
    return ((x << r) & MASK64) | (x >> (64 - r))


def _fmix64(k: int) -> int:
    k ^= k >> 33
    k = (k * 0xFF51AFD7ED558CCD) & MASK64
    k ^= k >> 33
    k = (k * 0xC4CEB9FE1A85EC53) & MASK64
    k ^= k >> 33
    return k


def murmurhash3_x64_128_bytes(data: bytes, seed: int = 0) -> bytes:
    c1 = 0x87C37B91114253D5
    c2 = 0x4CF5AD432745937F

    h1 = seed & MASK64
    h2 = seed & MASK64

    nblocks = len(data) // 16

    for i in range(nblocks):
        block = data[i * 16:(i + 1) * 16]

        k1 = int.from_bytes(block[0:8], "little")
        k2 = int.from_bytes(block[8:16], "little")

        k1 = (k1 * c1) & MASK64
        k1 = _rotl64(k1, 31)
        k1 = (k1 * c2) & MASK64
        h1 ^= k1

        h1 = _rotl64(h1, 27)
        h1 = (h1 + h2) & MASK64
        h1 = (h1 * 5 + 0x52DCE729) & MASK64

        k2 = (k2 * c2) & MASK64
        k2 = _rotl64(k2, 33)
        k2 = (k2 * c1) & MASK64
        h2 ^= k2

        h2 = _rotl64(h2, 31)
        h2 = (h2 + h1) & MASK64
        h2 = (h2 * 5 + 0x38495AB5) & MASK64

    tail = data[nblocks * 16:]

    k1 = 0
    k2 = 0

    for i, b in enumerate(tail[:8]):
        k1 ^= b << (8 * i)

    for i, b in enumerate(tail[8:]):
        k2 ^= b << (8 * i)

    if len(tail) > 8:
        k2 = (k2 * c2) & MASK64
        k2 = _rotl64(k2, 33)
        k2 = (k2 * c1) & MASK64
        h2 ^= k2

    if len(tail) > 0:
        k1 = (k1 * c1) & MASK64
        k1 = _rotl64(k1, 31)
        k1 = (k1 * c2) & MASK64
        h1 ^= k1

    length = len(data)

    h1 ^= length
    h2 ^= length

    h1 = (h1 + h2) & MASK64
    h2 = (h2 + h1) & MASK64

    h1 = _fmix64(h1)
    h2 = _fmix64(h2)

    h1 = (h1 + h2) & MASK64
    h2 = (h2 + h1) & MASK64

    return h1.to_bytes(8, "big") + h2.to_bytes(8, "big")


def murmur3_to_bytes(text: str) -> bytes:
    return murmurhash3_x64_128_bytes(text.encode("utf-8"))


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - len(data) % block_size
    return data + bytes([pad_len]) * pad_len


class RiskCaptchaCodec:
    def __init__(self) -> None:
        self._salt: str = ""
        self._v_token: str = ""

    @staticmethod
    def _extract_secret_key(v_voucher: str, secret_index: int) -> str:
        """
        还原 JS 里的 secretIndex 位扫描逻辑：
        - 扫描 0..31 位；
        - 找出被置 1 的 bit 位置；
        - token 长度 > 8 时先丢掉前 8 位；
        - 用前两个 set-bit 作为 substring(start, end)。
        """

        set_bits = [i for i in range(32) if secret_index & (1 << i)]

        if len(set_bits) < 2:
            raise ValueError(
                f"secret_index 至少需要两个 set bit，当前为: {secret_index}")

        start, end = set_bits[0], set_bits[1]

        token = v_voucher[8:] if len(v_voucher) > 8 else v_voucher
        return token[start:end]

    def __risk_captcha_dec__(self,
                             v_voucher: str, content: str) -> Dict[str, Any]:
        """
        Python 版 __risk_captcha_dec__。

        content 外层结构：
            base64("timestamp|salt|secretIndex|encrypted")

        encrypted 内层：
            base64(xor_encrypted_json_bytes)
        """

        decoded = b64decode(content).decode("latin1")
        parts = decoded.split("|")

        if len(parts) != 4:
            raise ValueError(
                f"content 解码后应有 4 段，实际为 {len(parts)} 段: {parts!r}")

        timestamp, salt, secret_index_raw, encrypted = parts

        secret_index = int(secret_index_raw)
        secret_key = self._extract_secret_key(v_voucher, secret_index)

        sha_hex = sha256((secret_key + timestamp).encode("utf-8")).hexdigest()
        xor_key = bytes.fromhex(sha_hex)[:16]

        encrypted_bytes = b64decode(encrypted)
        raw = bytes(
            encrypted_bytes[i] ^ xor_key[i % len(xor_key)]
            for i in range(len(encrypted_bytes))
        )

        data = loads(raw.decode("utf-8"))

        self._salt = salt

        self._v_token = data.get("token")
        data["token"] = self.obfuscate_token(self._v_token)

        return data

    @staticmethod
    def obfuscate_token(
            token: str,
            *,
            mask_byte: Optional[int] = None,
            salt8: Optional[bytes] = None,
    ) -> str:
        """
        VM 里的 token 混淆结构：
            mask_byte
            + token_bytes[i] ^ mask_byte ^ salt8[i % 8]
            + salt8

        即：
            base64(mask + mixed_token + salt8)
        """

        token_bytes = token.encode("utf-8")

        if salt8 is None:
            salt8 = os.urandom(8)

        if len(salt8) != 8:
            raise ValueError("salt8 必须是 8 字节")

        if mask_byte is None:
            mask_byte = os.urandom(1)[0]

        if not 0 <= mask_byte <= 255:
            raise ValueError("mask_byte 必须在 0..255")

        mixed = bytes(
            token_bytes[i] ^ mask_byte ^ salt8[i % 8]
            for i in range(len(token_bytes))
        )

        raw = bytes([mask_byte]) + mixed + salt8
        return b64encode(raw).decode("ascii")

    @staticmethod
    def encrypt_content(encrypted_token: str, salt: str,
                        params: Dict[str, Any]) -> str:
        """
        对应 VM 里的 encryptParams / AES-CBC 部分。

        明文：
            JSON.stringify(params)

        key:
            murmur3ToBytes(encrypted_token)

        iv:
            murmur3ToBytes(salt)

        返回：
            base64(AES-CBC(ciphertext))
        """

        params_string = dumps(params)

        plaintext = params_string.encode("utf-8")

        aes_key = murmur3_to_bytes(encrypted_token)
        iv = murmur3_to_bytes(salt)

        padded = pkcs7_pad(plaintext, 16)

        cipher = Cipher(
            algorithms.AES(aes_key),
            modes.CBC(iv),
        )

        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded) + encryptor.finalize()

        return b64encode(ciphertext).decode("ascii")

    def __risk_captcha_enc__(self, params: Dict[str, Any]) -> Dict[str, str]:
        """
        调用方期望的返回值：

            {
                "token": obfuscated_token,
                "content": aes_content_base64
            }

        注意：
        - params 会被原地追加 token；
        - params["token"] 是原始 _v_token；
        - 返回对象里的 token 是 obfuscated_token；
        - content 是 AES-CBC 加密后的 base64。
        """

        if not self._v_token:
            raise RuntimeError("缺少 _v_token，需要先执行 dec 初始化")

        if not self._salt:
            raise RuntimeError("缺少 _salt，需要先执行 dec 初始化")

        encrypted_token = self.obfuscate_token(self._v_token)

        # 贴近 JS 行为：原地修改传入对象。
        params["token"] = self._v_token

        content = self.encrypt_content(
            encrypted_token=encrypted_token,
            salt=self._salt,
            params=params,
        )

        return {
            "token": encrypted_token,
            "content": content,
        }

    def __risk_captcha_vail__(self, clear: bool = False) -> str:
        """
        VM 里 vail 更像读取当前 token 状态，不是服务端验证。
        这里实现为返回当前 _v_token；没有则返回空字符串。
        """
        if not clear:
            return self._v_token
        v_token, self._v_token, self._salt = self._v_token, "", ""
        return v_token
