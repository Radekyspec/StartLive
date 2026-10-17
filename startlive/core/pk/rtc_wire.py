"""RTC protobuf encoding via Google's runtime, with the existing dictionary API.

The verified, deliberately partial schema remains in ``constant.pk_schema``. Build the
message types at import time rather than maintaining another wire codec or a
second, potentially out-of-sync generated .proto definition.
"""
from struct import pack
import base64
import binascii

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.internal.encoder import _VarintBytes
from google.protobuf.message import DecodeError
from google.protobuf.unknown_fields import UnknownFieldSet

from startlive.core.constant.pk_schema import SCHEMA
from startlive.core.constant.pk_wire import SCALARS, MAX_MESSAGE, \
    PROTOBUF_FIELD_TYPES
from startlive.core.exceptions import PkProtocolError


def _message_classes():
    """Generate descriptors from the recovered field table, without protoc."""
    file = descriptor_pb2.FileDescriptorProto()
    file.name = "startlive/rtc_recovered.proto"
    file.package = "startlive.rtc"
    # Proto2 exposes scalar presence in ListFields. For ordinary proto3
    # fields encode() explicitly drops default values, matching the native
    # proto3 serializer; optional/oneof fields retain false and empty strings.
    file.syntax = "proto2"
    for name, fields in SCHEMA.items():
        message = file.message_type.add()
        message.name = name
        if any((len(field) > 3 and field[3] == "oneof") for field in fields):
            message.oneof_decl.add().name = "payload"
        for number, key, kind, *modes in fields:
            mode = modes[0] if modes else ""
            field = message.field.add()
            field.number, field.name = number, key
            field.label = (
                field.LABEL_REPEATED if mode in ("repeated", "packed")
                else field.LABEL_OPTIONAL)
            if kind in SCHEMA:
                field.type = field.TYPE_MESSAGE
                field.type_name = ".startlive.rtc." + kind
            else:
                field.type = PROTOBUF_FIELD_TYPES[kind]
            if mode == "oneof":
                field.oneof_index = 0
            if mode == "packed":
                field.options.packed = True
    pool = descriptor_pool.DescriptorPool()
    pool.Add(file)
    return {name: message_factory.GetMessageClass(
        pool.FindMessageTypeByName("startlive.rtc." + name)) for name in SCHEMA}


_MESSAGES = _message_classes()


def _unknown_wire(message):
    """Expose unknown fields in the previous list-of-hex shape.

    UnknownFieldSet is the protobuf runtime's decoder: only the small wire
    re-serialization below is needed for round-tripping unknown fields.
    Noncanonical varint spellings may be normalized by the official parser.
    """
    result = []
    for field in UnknownFieldSet(message):
        prefix = _VarintBytes((field.field_number << 3) | field.wire_type)
        if field.wire_type == 0:
            payload = _VarintBytes(field.data)
        elif field.wire_type == 1:
            payload = pack("<Q", field.data)
        elif field.wire_type == 2:
            payload = _VarintBytes(len(field.data)) + field.data
        elif field.wire_type == 5:
            payload = pack("<I", field.data)
        else:
            raise PkProtocolError("RTC unsupported unknown wire type")
        result.append((prefix + payload).hex())
    return result


def _to_dict(message):
    result = {}
    for field, value in message.ListFields():
        if field.is_repeated:
            values = value
        else:
            values = (value,)
        if field.type == field.TYPE_MESSAGE:
            converted = [_to_dict(item) for item in values]
        elif field.type == field.TYPE_BYTES:
            converted = [{"hex": item.hex()} for item in values]
        elif field.type == field.TYPE_STRING:
            # The proto2 runtime may expose malformed UTF-8 as bytes instead
            # of rejecting it; the previous RTC decoder explicitly rejected it.
            if any(not isinstance(item, str) for item in values):
                raise PkProtocolError("RTC invalid UTF-8")
            converted = list(values)
        else:
            converted = list(values)
        result[field.name] = converted if field.is_repeated else converted[0]
    unknown = _unknown_wire(message)
    if unknown:
        result["_unknown_wire"] = unknown
    return result


def decode(name, raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_MESSAGE:
        raise PkProtocolError("RTC message exceeds limits or is not binary")
    message = _MESSAGES[name]()
    try:
        message.ParseFromString(raw)
        return _to_dict(message)
    except (DecodeError, UnicodeDecodeError, ValueError) as error:
        raise PkProtocolError("RTC protobuf decoding failed") from error


def _checked_scalar(value, kind):
    if kind == "bool":
        if type(value) is not bool:
            raise PkProtocolError("Expected RTC boolean")
        return value
    bits = 32 if kind.endswith("32") else 64
    low = -(1 << (bits - 1)) if kind.startswith("int") else 0
    high = 1 << (bits - 1) if kind.startswith("int") else 1 << bits
    if type(value) is not int or not low <= value < high:
        raise PkProtocolError("RTC scalar out of range")
    return value


def _apply_field(message, key, kind, mode, item):
    if kind in SCALARS:
        scalar = _checked_scalar(item, kind)
        if mode in ("repeated", "packed"):
            getattr(message, key).append(scalar)
        elif scalar or mode in ("optional", "oneof"):
            setattr(message, key, scalar)
    elif kind == "string":
        if not isinstance(item, str):
            raise PkProtocolError("Expected RTC string")
        if mode in ("repeated", "packed"):
            getattr(message, key).append(item)
        elif item or mode in ("optional", "oneof"):
            setattr(message, key, item)
    elif kind == "bytes":
        if not isinstance(item, dict) or not isinstance(item.get("hex"), str):
            raise PkProtocolError("Expected RTC binary hex value")
        try:
            raw = bytes.fromhex(item["hex"])
        except ValueError:
            raise PkProtocolError("Invalid RTC binary hex value") from None
        if mode in ("repeated", "packed"):
            getattr(message, key).append(raw)
        elif raw or mode in ("optional", "oneof"):
            setattr(message, key, raw)
    else:
        # The recovered schema uses nested objects (including empty objects)
        # as present length-delimited fields. CopyFrom preserves that presence.
        child = _MESSAGES[kind]()
        unknown = _populate_message(child, kind, item)
        if unknown:
            # Unknown fragments may contain known tags; merge them with the
            # same protobuf semantics as the previous encode/parse round trip.
            child.MergeFromString(unknown)
        if mode == "repeated":
            getattr(message, key).add().CopyFrom(child)
        else:
            getattr(message, key).CopyFrom(child)


def _populate_message(message, name, values):
    if not isinstance(values, dict):
        raise PkProtocolError("RTC message must be a dictionary")
    allowed = {f[1] for f in SCHEMA[name]} | {"_unknown_wire"}
    if values.keys() - allowed:
        raise PkProtocolError("Unknown RTC schema field")
    chosen = 0
    for _, key, kind, *modes in SCHEMA[name]:
        if key not in values:
            continue
        mode = modes[0] if modes else ""
        if mode == "oneof":
            chosen += 1
            if chosen > 1:
                raise PkProtocolError("Multiple RTC oneof payloads")
        if mode in ("repeated", "packed"):
            items = values[key]
            if not isinstance(items, (list, tuple)):
                raise PkProtocolError("RTC repeated field must be a sequence")
        else:
            items = (values[key],)
        for item in items:
            _apply_field(message, key, kind, mode, item)
    unknown = values.get("_unknown_wire", [])
    if not isinstance(unknown, (list, tuple)):
        raise PkProtocolError("RTC unknown wire must be a list")
    try:
        unknown_wire = b"".join(bytes.fromhex(item) for item in unknown)
    except (TypeError, ValueError):
        raise PkProtocolError("Invalid RTC unknown wire hex") from None
    if message.ByteSize() + len(unknown_wire) > MAX_MESSAGE:
        raise PkProtocolError("RTC message exceeds limits")
    return unknown_wire


def encode(name, values):
    message = _MESSAGES[name]()
    unknown = _populate_message(message, name, values)
    return message.SerializeToString(deterministic=True) + unknown


def decode_ticket(encoded, *, uid, channel_id):
    if not isinstance(encoded, str) or len(encoded) > MAX_MESSAGE:
        raise PkProtocolError("Invalid RTC access token")
    try:
        data = decode("AccessToken", base64.b64decode(encoded, validate=True))
    except (binascii.Error, ValueError):
        raise PkProtocolError("Invalid RTC access token encoding") from None
    if data.get("uid") != uid or data.get("channel_id") != channel_id:
        raise PkProtocolError("RTC 票据与当前登录用户或频道不符")
    if any(not data.get(key) for key in
           ("token", "addr", "fingerprint", "password")):
        raise PkProtocolError("RTC 票据缺少连接参数")
    return data
