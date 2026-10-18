"""Supported source fields and limits for offline configuration conversion."""

MAX_CONFIG_BYTES = 32 * 1024 * 1024

FILTERED_SCENE_PREFIXES = ("Vertical", "wDouble", "xDouble")

SOURCE_IDS = frozenset({
    "scene", "group", "image_source", "color_source", "slideshow",
    "browser_source", "ffmpeg_source", "vlc_source", "text_gdiplus",
    "text_ft2_source", "monitor_capture", "window_capture", "game_capture",
    "dshow_input", "wasapi_input_capture", "wasapi_output_capture",
    "wasapi_process_output_capture",
})

FILTER_IDS = frozenset({
    "mask_filter", "crop_filter", "gain_filter", "color_filter", "scale_filter",
    "scroll_filter", "color_key_filter", "chroma_key_filter",
    "sharpness_filter",
    "noise_gate_filter", "noise_suppress_filter", "compressor_filter",
    "limiter_filter", "expander_filter", "luma_key_filter", "clut_filter",
    "async_delay_filter", "gpu_delay", "invert_polarity_filter",
    "upward_compressor_filter", "hdr_tonemap_filter", "basic_eq_filter",
})

TRANSITION_IDS = frozenset({
    "cut_transition", "fade_transition", "swipe_transition", "slide_transition",
    "fade_to_color_transition", "wipe_transition", "obs_stinger_transition",
})

AUDIO_KEYS = {
    "Desktop Audio": "DesktopAudioDevice1",
    "Desktop Audio 2": "DesktopAudioDevice2",
    "Mic/Aux": "AuxAudioDevice1",
    "Mic/Aux 2": "AuxAudioDevice2",
    "Mic/Aux 3": "AuxAudioDevice3",
    "Mic/Aux 4": "AuxAudioDevice4",
}

# Only source serialization fields; no application preferences or credentials.
SOURCE_FIELDS = frozenset({
    "name", "uuid", "id", "versioned_id", "settings", "mixers", "sync",
    "flags", "volume", "balance", "enabled", "muted", "push-to-mute",
    "push-to-mute-delay", "push-to-talk", "push-to-talk-delay", "hotkeys",
    "deinterlace_mode", "deinterlace_field_order", "monitoring_type",
})

ITEM_FIELDS = frozenset({
    "name", "source_uuid", "visible", "locked", "rot", "align", "pos",
    "scale", "scale_ref", "bounds", "bounds_type", "bounds_align",
    "bounds_crop", "crop_left", "crop_top", "crop_right", "crop_bottom",
    "id", "group_item_backup", "scale_filter", "blend_method", "blend_type",
})
