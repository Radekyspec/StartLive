from enum import StrEnum, unique

from . import KEYRING_APP_SETTINGS, KEYRING_SETTINGS


@unique
class SettingsName(StrEnum):
    APP = "app"
    OBS = "obs"
    PK_ENCODER = "pk_encoder"


# Public preference names are closed; callers cannot choose arbitrary paths.
_SETTINGS_FILES = {
    SettingsName.APP: "app_settings.json",
    SettingsName.OBS: "obs_settings.json",
    SettingsName.PK_ENCODER: "pk_encoder_settings.json",
}

# Only app and OBS settings support the legacy keyring representation.
_LEGACY_SETTINGS_KEYS = {
    SettingsName.APP: KEYRING_APP_SETTINGS,
    SettingsName.OBS: KEYRING_SETTINGS,
}
