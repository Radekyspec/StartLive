from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class RtcTransportPolicy:
    """Resolved Contract37 application options, separate from token TURN data.

    Remote values come from a successful resource response. StartLive keeps
    its own automatic any-address option disabled by default; no installed
    LiveHime setting, cache or DLL is needed. Fetching settings does not apply
    them to an already-created provider.

    Contract38: switch_new enables the native controller/monitor; the separate
    UDP/TCP/TURN switch and disable_udp feed different monitor fields. Its
    action matrix starts after guards whose full history is still unresolved.
    These options do not define a retry timer, failure count or recovery result.
    StartLive retains the tuning fields as resource metadata, not connection
    prerequisites. Only disable_udp selects the remote candidate protocol;
    local gathering and pair selection follow StartLive's provider policy.
    """
    disable_udp: bool
    enable_ice_candidate_switch_new: bool
    enable_udp_tcp_turn_switch: bool
    enable_any_address_ice_ports: bool
    auto_enable_any_address_ice_ports: bool = False

    def __post_init__(self):
        if any(type(getattr(self, field.name)) is not bool for field in
               fields(self)):
            raise ValueError("RTC transport options must be resolved booleans")

    @property
    def any_address_ice_ports(self):
        return self.enable_any_address_ice_ports or self.auto_enable_any_address_ice_ports
