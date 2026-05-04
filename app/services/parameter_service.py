from collections import defaultdict
from typing import Any

from app.core.json_store import JsonStore
from app.services.config_service import ConfigService


class ParameterService:
    def __init__(self, store: JsonStore | None = None, config_service: ConfigService | None = None) -> None:
        self.store = store or JsonStore()
        self.config_service = config_service or ConfigService(store=self.store)

    def load_page_data(self) -> dict[str, Any]:
        parameters = self.config_service.get_binary_parameters()
        groups = ["basic", "latency", "download", "output", "advanced"]
        grouped_parameters, command_parts = self._build_grouped_parameters(parameters)
        ordered_groups = [
            {
                "key": group,
                "label": self._group_label(group),
                "parameters": grouped_parameters.get(group, []),
            }
            for group in groups
        ]
        return {
            "groups": ordered_groups,
            "command_preview": self.build_command_preview(),
            "total_params": sum(len(g["parameters"]) for g in ordered_groups),
        }

    def build_runtime_context(self) -> dict[str, Any]:
        return self.config_service.get_runtime_context()

    def build_command_preview(self, binary_path: str = "cfst") -> str:
        return self.config_service.build_command_preview(binary_path)

    def _build_grouped_parameters(
        self,
        parameters: dict[str, Any],
    ) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
        grouped_parameters: dict[str, list[dict[str, Any]]] = defaultdict(list)
        command_parts: list[str] = []

        group_mapping = {
            "thread_count": "basic",
            "test_count": "basic",
            "download_count": "download",
            "download_time": "download",
            "port": "basic",
            "url": "basic",
            "httping": "advanced",
            "httping_code": "advanced",
            "cfcolo": "advanced",
            "latency_limit": "latency",
            "latency_lower": "latency",
            "packet_loss_limit": "latency",
            "speed_limit": "download",
            "display_count": "output",
            "ip_file": "output",
            "ip_list": "output",
            "result_file": "output",
            "disable_download": "download",
            "all_ip": "advanced",
            "debug": "advanced",
        }

        for key, param in parameters.items():
            group = group_mapping.get(key, "advanced")
            enabled = param.get("enabled", False)
            value = param.get("value")
            param_type = param.get("type", "string")
            flag = param.get("flag", "")

            validation = {}
            if "min" in param:
                validation["min"] = param["min"]
            if "max" in param:
                validation["max"] = param["max"]

            display_parameter = {
                "key": key,
                "label": param.get("description", key),
                "cli_flag": flag,
                "type": param_type,
                "default": value,
                "enabled": enabled,
                "value": value,
                "validation": validation,
                "validation_text": self._build_validation_text(validation),
            }
            grouped_parameters[group].append(display_parameter)

            if enabled:
                command_parts.extend(self._build_command_part(flag, param_type, value))

        return grouped_parameters, command_parts

    def _build_command_part(self, flag: str, param_type: str, value: Any) -> list[str]:
        if not flag:
            return []
        if param_type == "boolean":
            return [flag] if value else []
        if value is not None and value != "":
            return [flag, str(value)]
        return []

    def _build_validation_text(self, validation: dict[str, Any]) -> str:
        parts: list[str] = []
        if "min" in validation:
            parts.append(f"最小值 {validation['min']}")
        if "max" in validation:
            parts.append(f"最大值 {validation['max']}")
        return "，".join(parts) if parts else "无额外限制"

    def _group_label(self, group: str) -> str:
        mapping = {
            "basic": "基础参数",
            "latency": "延迟测试",
            "download": "下载测速",
            "output": "输出参数",
            "advanced": "高级参数",
        }
        return mapping.get(group, group)
