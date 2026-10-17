from google.protobuf import descriptor_pb2

SCALARS = frozenset({"uint64", "uint32", "int64", "int32", "bool"})

MAX_MESSAGE = 262144

PROTOBUF_FIELD_TYPES = {
    "uint64": descriptor_pb2.FieldDescriptorProto.TYPE_UINT64,
    "uint32": descriptor_pb2.FieldDescriptorProto.TYPE_UINT32,
    "int64": descriptor_pb2.FieldDescriptorProto.TYPE_INT64,
    "int32": descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
    "bool": descriptor_pb2.FieldDescriptorProto.TYPE_BOOL,
    "string": descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    "bytes": descriptor_pb2.FieldDescriptorProto.TYPE_BYTES,
}
