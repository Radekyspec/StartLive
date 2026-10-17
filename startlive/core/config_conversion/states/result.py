from dataclasses import dataclass


@dataclass
class ConversionResult:
    collection: dict
    warnings: list[str]
    scene_count: int
    source_count: int
    skipped_sources: int

    def summary(self) -> str:
        lines = [
            f"场景集合：{self.collection['name']}",
            f"保留 {self.scene_count} 个场景、{self.source_count} 个素材/音频源；"
            f"跳过 {self.skipped_sources} 个不兼容源。",
        ]
        resolution = self.collection.get("resolution")
        if resolution:
            lines.append(f"参考画布：{resolution['x']} × {resolution['y']}")
        lines.append("\n转换提示：")
        lines.extend(f"• {message}" for message in self.warnings)
        if not self.warnings:
            lines.append("未发现不兼容项目。")
        lines.append("\n导出后，在 OBS 中选择「场景集合 → 导入」。"
                     "请核对画布尺寸、音频设备和素材路径；素材文件不会打包。")
        return "\n".join(lines)
