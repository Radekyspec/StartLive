"""Verified room bootstrap and repeated-sequence ACK forms."""
from startlive.core import constant
from startlive.core.sign.app_sign import encode_payload, livehime_sign, \
    sign_preimage


def bootstrap_query(*, access_key: str, room_id: int, user_type: int,
                    is_anchor: bool,
                    version: str, timestamp: int) -> str:
    """getDanmuInfo uses five common fields, unlike the PK business builder.

    user_type/is_anchor must come from the caller's confirmed flow. The native
    header/cookie policy is still pending; this function makes no HTTP request.
    """
    if type(user_type) is not int or type(is_anchor) is not bool:
        raise TypeError("Push login requires explicit user_type and is_anchor")
    signed = livehime_sign({
        "access_key": access_key,
        "version": version, "ts": str(timestamp), "room_id": str(room_id),
        "user_type": str(user_type),
        "is_anchor": "true" if is_anchor else "false",
    }, build=False, native_wire=True)
    return encode_payload(signed, native_wire=True)


def sequence_ack_form(*, access_key: str, csrf: str, sequences, version: str,
                      timestamp: int) -> str:
    sequences = tuple(sequences)
    if not sequences or any(
            type(value) is not int or not 0 < value <= 0xFFFFFFFF for value in
            sequences):
        raise ValueError("Sequence ACK requires nonzero uint32 sequences")
    pairs = [("appkey", constant.APP_KEY), ("ts", str(timestamp)),
             ("platform", "pc_link"),
             ("version", version), ("access_key", access_key),
             ("terminal", "1")]
    pairs.extend(("sequence", str(value)) for value in sorted(set(sequences)))
    signature = sign_preimage(encode_payload(pairs, native_wire=True))
    pairs.extend((("sign", signature), ("csrf_token", csrf), ("csrf", csrf)))
    return encode_payload(pairs, native_wire=True)
