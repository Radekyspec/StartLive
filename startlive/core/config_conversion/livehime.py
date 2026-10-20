"""Convert Livehime's libobs JSON without modifying either application's data.

The supported schema is the observed untitled[v2].json / Scene Collection
format. Unknown plugin IDs are deliberately omitted, never guessed.
"""
import json
import math
import os
import re
from copy import deepcopy
from pathlib import Path

from startlive.core.constant.config_conversion import (
    MAX_CONFIG_BYTES,
    FILTERED_SCENE_PREFIXES,
    SOURCE_IDS,
    FILTER_IDS,
    TRANSITION_IDS,
    AUDIO_KEYS,
    SOURCE_FIELDS,
    ITEM_FIELDS,
)
from .states.result import ConversionResult


class ConversionError(ValueError):
    """A readable error suitable for the conversion dialog."""


def default_data_root() -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "bililive" / "User Data" if local else None


def discover_configs(root: Path | None = None) -> list[Path]:
    """Bounded discovery in User Data, an account, or Scene Collection folder.

    An install directory is accepted too, but per-user configuration is normally
    in LOCALAPPDATA. Backups remain manually selectable, not auto-selected.
    """
    roots = [Path(root)] if root is not None else []
    default = default_data_root()
    if root is None and default is not None:
        roots.append(default)
    candidates = set()
    for base in roots:
        if base.is_file():
            candidates.add(base)
            continue
        for directory in (base, base / "User Data"):
            if not directory.is_dir():
                continue
            accounts = [directory]
            accounts.extend(p for p in directory.iterdir()
                            if p.is_dir() and p.name.isdecimal())
            for account in accounts:
                for name in ("untitled.json", "untitledv2.json"):
                    p = account / name
                    if p.is_file():
                        candidates.add(p)
                collection = account / "Scene Collection"
                if collection.is_dir():
                    candidates.update(collection.glob("*.json"))
            if directory.name == "Scene Collection":
                candidates.update(directory.glob("*.json"))
    return sorted(candidates, key=lambda p: (
        p.name != "support_group_collection.json", -p.stat().st_mtime, str(p)))


def read_config(path: Path) -> dict:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_CONFIG_BYTES + 1)
    if len(raw) > MAX_CONFIG_BYTES:
        raise ConversionError("配置文件超过 32 MiB，请选择场景配置 JSON。")
    try:
        encoding = "utf-16" if raw.startswith(
            (b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        data = json.loads(raw.decode(encoding),
                          parse_constant=_invalid_constant,
                          parse_float=_finite_float)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ConversionError(
            "无法解析场景 JSON；请确认文件完整，必要时退出直播姬后重试。") from exc
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise ConversionError(
            "不是支持的场景配置：需要包含 sources 数组的 JSON 对象。")
    return data


def _invalid_constant(value):
    raise ValueError(f"Invalid JSON number: {value}")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number out of range")
    return number


def _objects(value, label):
    if not isinstance(value, list) or any(
            not isinstance(v, dict) for v in value):
        raise ConversionError(f"{label} 必须是对象数组。")
    return value


def _dimensions(x, y):
    return (isinstance(x, (int, float)) and not isinstance(x, bool)
            and isinstance(y, (int, float)) and not isinstance(y, bool)
            and 1 <= x <= 16384 and 1 <= y <= 16384
            and int(x) == x and int(y) == y)


def infer_resolution(data: dict) -> tuple[int, int] | None:
    """Use scene coordinates, not output/encoder preferences or helper canvases."""
    resolution = data.get("resolution", {})
    if isinstance(resolution, dict) and _dimensions(resolution.get("x"),
                                                    resolution.get("y")):
        return int(resolution["x"]), int(resolution["y"])
    sizes = set()
    for source in _objects(data.get("sources", []), "sources"):
        settings = source.get("settings", {})
        if source.get("id") != "scene" or not isinstance(settings,
                                                         dict) or settings.get(
            "custom_size"):
            continue
        for item in _objects(settings.get("items", []), "场景 items"):
            size = item.get("scale_ref", {})
            if isinstance(size, dict) and _dimensions(size.get("x"),
                                                      size.get("y")):
                sizes.add((int(size["x"]), int(size["y"])))
    # Different horizontal/vertical canvases cannot be inferred unambiguously.
    return next(iter(sizes)) if len(sizes) == 1 else None


def convert_collection(data: dict, *, name: str = "直播姬转换",
                       resolution: tuple[int, int] | None = None,
                       source_dir: Path | None = None,
                       filter_prefixed_scenes: bool = False) -> ConversionResult:
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise ConversionError("不是支持的直播姬场景配置。")
    if not name.strip():
        raise ConversionError("请输入场景集合名称。")
    warnings = []
    skipped = 0

    def warn(message):
        if message not in warnings:
            warnings.append(message)

    def paths(settings, label):
        # Only known local asset fields; never rewrite URLs, device IDs or windows.
        for key in ("file", "local_file", "text_file", "image_path", "path"):
            value = settings.get(key)
            if not isinstance(value, str) or not value or re.match(
                    r"^[a-zA-Z][\w+.-]*://", value):
                continue
            p = Path(value)
            if not p.is_absolute():
                candidate = source_dir / p if source_dir is not None else None
                if candidate is not None and candidate.is_file():
                    settings[key] = str(candidate.resolve())
                else:
                    warn(
                        f"{label}：相对素材路径 {value} 无法定位，请在 OBS 中重新选择。")
            elif not p.exists():
                warn(f"{label}：素材不存在：{value}")
        for key in ("files", "playlist"):
            for entry in settings.get(key, []) if isinstance(settings.get(key),
                                                             list) else []:
                if isinstance(entry, dict) and isinstance(entry.get("value"),
                                                          str):
                    proxy = {"file": entry["value"]}
                    paths(proxy, label)
                    entry["value"] = proxy["file"]

    def plugin(raw, allowed, kind):
        nonlocal skipped
        identifier = raw.get("id")
        label = raw.get("name")
        if not isinstance(identifier, str) or not isinstance(label,
                                                             str) or not label:
            raise ConversionError(f"{kind} 缺少有效的 id 或 name。")
        settings = raw.get("settings", {})
        if not isinstance(settings, dict):
            raise ConversionError(f"{label} 的 settings 必须是对象。")
        # GUI-created Livehime 8.7 camera sources serialize as dshow_input.
        # A string found in a DLL alone does not establish a source-ID alias.
        if identifier not in allowed:
            warn(
                f"跳过{kind}「{label}」（{identifier}）：当前转换器尚未确认其 OBS 兼容性。")
            if kind == "源":
                skipped += 1
            return None
        out = {k: deepcopy(v) for k, v in raw.items() if
               k in SOURCE_FIELDS and k != "settings"}
        out["settings"] = deepcopy(settings)
        for key in ("source_id", "hotkey_value", "audio_render_error",
                    "audio_device_name"):
            out["settings"].pop(key, None)
        if out.get("versioned_id") and not re.fullmatch(
                re.escape(identifier) + r"(?:_v\d+)?",
                str(out["versioned_id"])):
            out["versioned_id"] = identifier
            warn(f"「{label}」的插件版本标识不兼容，已回退到 {identifier}。")
        if isinstance(out.get("mixers"), int):
            out["mixers"] &= 0x3F  # OBS exposes six audio tracks.
        filters = []
        for filt in _objects(raw.get("filters", []), f"{label} filters"):
            converted = plugin(filt, FILTER_IDS, "滤镜")
            if converted is not None:
                filters.append(converted)
        if filters:
            out["filters"] = filters
        paths(out["settings"], label)
        if identifier == "vlc_source":
            warn(f"「{label}」需要 OBS 可用的 VLC 视频源插件。")
        if identifier == "browser_source":
            warn(
                f"「{label}」的浏览器会话不会迁移；直播姬内置网页可能需要重新登录或更换地址。")
        return out

    raw_sources = _objects(data["sources"], "sources") + _objects(
        data.get("groups", []), "groups")
    if filter_prefixed_scenes:
        retained, filtered = [], 0
        for source in raw_sources:
            if (source.get("id") == "scene" and isinstance(source.get("name"),
                                                           str)
                    and source["name"].startswith(FILTERED_SCENE_PREFIXES)):
                filtered += 1
            else:
                retained.append(source)
        raw_sources = retained
        warn(
            f"按名称前缀过滤了 {filtered} 个场景（{'、'.join(FILTERED_SCENE_PREFIXES)}，区分大小写）。")
        if filtered and not any(s.get("id") == "scene" for s in raw_sources):
            raise ConversionError(
                "过滤后没有可导出的场景，请取消前缀过滤或选择其他配置。")
    converted = []
    for source in raw_sources:
        result = plugin(source, SOURCE_IDS, "源")
        if result is not None:
            converted.append(result)
    audio = {}
    for legacy, standard in AUDIO_KEYS.items():
        raw = data.get(standard, data.get(legacy))
        if raw is not None:
            if not isinstance(raw, dict):
                raise ConversionError(f"{legacy} 音频配置必须是对象。")
            result = plugin(raw, SOURCE_IDS, "源")
            if result is not None:
                audio[standard] = result
    names, uuids = {}, {}
    for source in converted + list(audio.values()):
        label, uuid = source["name"], source.get("uuid")
        if uuid is not None and not isinstance(uuid, str):
            raise ConversionError(f"{label} 的 UUID 必须是字符串。")
        if label in names or (uuid and uuid in uuids):
            raise ConversionError(
                f"源名称或 UUID 重复：{label}，无法可靠关联场景。")
        names[label] = source
        if uuid:
            uuids[uuid] = source

    scenes = [s for s in converted if s["id"] == "scene"]
    if not scenes:
        raise ConversionError("配置中没有可转换的 OBS 场景。")
    for source in converted:
        if source["id"] not in ("scene", "group"):
            continue
        settings = source["settings"]
        items = []
        raw_items = _objects(settings.get("items", []),
                             f"{source['name']} items")
        for item in raw_items:
            if item.get("group_item_backup"):
                continue  # OBS ignores these duplicate legacy flattened items.
            ref_uuid, ref_name = item.get("source_uuid"), item.get("name")
            if ref_uuid is not None and not isinstance(ref_uuid, str):
                raise ConversionError("场景项目的 source_uuid 必须是字符串。")
            if ref_name is not None and not isinstance(ref_name, str):
                raise ConversionError("场景项目的 name 必须是字符串。")
            target = uuids.get(ref_uuid) or names.get(ref_name)
            if target is None:
                warn(
                    f"场景「{source['name']}」跳过无法引用的素材「{ref_name or ref_uuid}」。")
                continue
            cleaned = {k: deepcopy(v) for k, v in item.items() if
                       k in ITEM_FIELDS}
            for absolute, relative in (("pos", "pos_rel"),
                                       ("scale", "scale_rel"),
                                       ("bounds", "bounds_rel")):
                if relative in item and absolute not in item:
                    raise ConversionError(
                        "此配置只有相对坐标，无法按直播姬绝对坐标格式转换。")
            cleaned["name"] = target["name"]
            if target.get("uuid"):
                cleaned["source_uuid"] = target["uuid"]
            else:
                cleaned.pop("source_uuid", None)
            for key in ("show_transition", "hide_transition"):
                transition = item.get(key)
                if transition and isinstance(transition,
                                             dict) and transition.get("id"):
                    raw_transition = {**transition,
                                      "settings": transition.get("transition",
                                                                 {})}
                    tr = plugin(raw_transition, TRANSITION_IDS, "转场")
                    if tr:
                        tr["transition"] = tr.pop("settings")
                        tr["duration"] = transition.get("duration", 300)
                        cleaned[key] = tr
            items.append(cleaned)
        if not items and any(not i.get("group_item_backup") for i in raw_items):
            warn(
                f"「{source['name']}」的全部场景项目已被跳过，转换后为空，请在 OBS 中检查。")
        source["settings"] = {k: v for k, v in settings.items()
                              if k in ("custom_size", "cx", "cy", "id_counter")}
        source["settings"]["items"] = items

    # Reject cycles instead of producing collections OBS cannot load reliably.
    visiting, visited = set(), set()

    def visit(source):
        label = source["name"]
        if label in visiting:
            raise ConversionError(f"场景或分组存在循环引用：{label}")
        if label in visited or source["id"] not in ("scene", "group"):
            return
        visiting.add(label)
        for item in source["settings"]["items"]:
            visit(names[item["name"]])
        visiting.remove(label)
        visited.add(label)

    try:
        for source in converted:
            visit(source)
    except RecursionError as exc:
        raise ConversionError("场景嵌套层数过多。") from exc

    scene_names = {s["name"] for s in scenes}
    order = []
    for entry in _objects(data.get("scene_order", []), "scene_order"):
        label = entry.get("name")
        if isinstance(label,
                      str) and label in scene_names and label not in order:
            order.append(label)
    order.extend(s["name"] for s in scenes if s["name"] not in order)
    current = data.get("current_scene")
    if not isinstance(current, str) or current not in scene_names:
        current = order[0]
        warn("当前场景不存在，已选择第一个保留的场景。")
    transitions = []
    for raw in _objects(data.get("transitions", []), "transitions"):
        result = plugin(raw, TRANSITION_IDS, "转场")
        if result is not None:
            transitions.append(result)
    if not transitions:
        transitions = [
            {"name": "淡入淡出", "id": "fade_transition", "settings": {}}]
    transition_name = data.get("current_transition")
    if transition_name not in [t["name"] for t in transitions]:
        transition_name = next(
            (t["name"] for t in transitions if t["id"] == "fade_transition"),
            transitions[0]["name"])
    duration = data.get("transition_duration_v2",
                        data.get("transition_duration", 300))
    if not isinstance(duration, int) or isinstance(duration,
                                                   bool) or not 0 <= duration <= 20000:
        duration = 300
        warn("无效的转场时长已改为 300 毫秒。")
    collection = {
        "name": name.strip(), "current_scene": current,
        "current_program_scene": current,
        "scene_order": [{"name": s} for s in order],
        "sources": [s for s in converted if s["id"] != "group"],
        "groups": [s for s in converted if s["id"] == "group"],
        "transitions": transitions, "current_transition": transition_name,
        "transition_duration": duration, "quick_transitions": [],
        "saved_projectors": [], "version": 1, **audio,
    }
    resolution = resolution or infer_resolution(
        {**data, "sources": raw_sources})
    if resolution is not None:
        if len(resolution) != 2 or not _dimensions(*resolution):
            raise ConversionError("画布宽高必须是 1–16384 的整数。")
        collection["resolution"] = {"x": int(resolution[0]),
                                    "y": int(resolution[1])}
    else:
        warn("无法确定原画布尺寸，请将 OBS 基础画布设置为直播姬原尺寸。")
    if any(s["settings"].get("custom_size") for s in scenes):
        warn("已保留自定义尺寸的嵌套场景；直播姬横竖屏、双屏输出模式不会迁移。")
    if any(raw.get("private_settings") for raw in raw_sources):
        warn("已忽略源的私有设置（可能包含直播姬效果或场景转场覆盖）。")
    return ConversionResult(collection, warnings, len(scenes),
                            sum(s["id"] not in ("scene", "group") for s in
                                converted) + len(audio), skipped)


def export_collection(result: ConversionResult, destination: Path) -> Path:
    """Create a new export; never overwrite a source or an existing OBS file."""
    destination = Path(destination)
    if destination.suffix.lower() != ".json":
        raise ConversionError("导出文件必须使用 .json 扩展名。")
    payload = json.dumps(result.collection, ensure_ascii=False, indent=2,
                         allow_nan=False) + "\n"
    # Exclusive creation also protects against a path changing after the dialog.
    stream = destination.open("x", encoding="utf-8", newline="\n")
    try:
        with stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination
