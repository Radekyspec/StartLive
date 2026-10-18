"""SDP direction rules and simulcast parsing pattern."""
import re

SDP_DIRECTIONS = {"a=sendonly", "a=recvonly", "a=sendrecv", "a=inactive"}

SDP_DIRECTION_PAIRS = {("sendonly", "recvonly"), ("recvonly", "sendonly"),
                       ("sendrecv", "sendrecv"), ("inactive", "inactive"),
                       ("", "")}

SDP_SIMULCAST_RE = re.compile(r"\n*(a=simulcast:)(send|recv)([^\r\n]+)")
