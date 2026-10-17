"""Codec-independent output geometry for a PK video sender."""
from fractions import Fraction

MAX_ENCODER_LATENCY_SECONDS = Fraction(1, 4)

PK_PACER_BURST_BYTES = 10400
PK_PACER_REFILL_SECONDS = 0.002
PK_PACER_RATE_FACTOR = 2.5
