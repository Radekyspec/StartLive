from dataclasses import dataclass

from startlive.core.constant.pk_user_settings import PK_SETTING_SWITCH_FIELDS
from startlive.core.pk.states.preferences import PkPreferenceValues


@dataclass(frozen=True, slots=True)
class PkUserSettingsSnapshot:
    """Config values, including LiveHime's zero fallback for null punishment options."""
    preferences: PkPreferenceValues
    duration_options: tuple[int, ...]
    show_score: int
    punish_time: int
    punish_time_options: tuple[int, ...]

    def business_fields(self) -> dict[str, str]:
        fields = {wire: str(int(getattr(self.preferences, semantic)))
                  for semantic, wire in PK_SETTING_SWITCH_FIELDS.items()}
        return fields | {"pk_time": str(self.preferences.duration),
                         "show_score": str(self.show_score),
                         "pk_punish_time": str(self.punish_time),
                         "show_pk_play_text": "2"}


@dataclass(frozen=True, slots=True)
class PkUserSettingsSaved:
    snapshot: PkUserSettingsSnapshot
    message: str = ""
