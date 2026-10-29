"""Reusable push subsystem, independent of PK and the GUI.

Provides Goim handshake, framing and compression (wire), protocol dispatch
(protocol), HTTP (api), connections (client and connection), and worker adapters
(workers/danmaku). Extend it with a DanmakuProtocol subclass supplied through
protocol_factory. PK is currently the only consumer.

DanmakuConnection owns two WorkerManager jobs: a socket worker and a separate
HTTP acknowledgement worker. Client owns the Goim TCP connection, authentication,
21-second heartbeat, reconnect and token refresh; it delivers DanmakuMessage
envelopes without importing any PK or GUI code. Three silent heartbeat intervals
trigger reconnect, preserving the dedupe context unless the token has expired.

Use danmaku.states.models.DanmakuIdentity to bind every job to one captured account. Callbacks
run through the supplied manager's dispatcher. start/stop only submit work or
signal cancellation; session/socket creation and cleanup stay in the workers.
PK supplies its own protocol subclass solely to decode business events.
"""
