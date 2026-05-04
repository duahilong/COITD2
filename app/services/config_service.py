from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.json_store import JsonStore
from app.schemas.files import MASTER_CONFIG_FILE


class ConfigService:
    def __init__(self, store: JsonStore | None = None) -> None:
        self.store = store or JsonStore()

    def load_master_config(self) -> dict[str, Any]:
        if self.store.exists(MASTER_CONFIG_FILE):
            return self.store.read(MASTER_CONFIG_FILE)
        return self._create_default_config()

    def save_master_config(self, config: dict[str, Any]) -> None:
        config["timestamps"]["updated_at"] = self._now()
        self.store.write(MASTER_CONFIG_FILE, config)

    def get_section(self, section: str) -> dict[str, Any]:
        config = self.load_master_config()
        return config.get("sections", {}).get(section, {})

    def update_section(self, section: str, data: dict[str, Any]) -> dict[str, Any]:
        config = self.load_master_config()
        if "sections" not in config:
            config["sections"] = {}
        config["sections"][section] = data
        self.save_master_config(config)
        return config

    def get_binary_config(self) -> dict[str, Any]:
        return self.get_section("binary")

    def update_binary_config(self, config_data: dict[str, Any]) -> dict[str, Any]:
        return self.update_section("binary", config_data)

    def get_binary_parameters(self) -> dict[str, Any]:
        binary = self.get_binary_config()
        return binary.get("parameters", {})

    def update_binary_parameters(self, parameters: dict[str, Any]) -> dict[str, Any]:
        config = self.load_master_config()
        if "sections" not in config:
            config["sections"] = {}
        if "binary" not in config["sections"]:
            config["sections"]["binary"] = {}
        config["sections"]["binary"]["parameters"] = parameters
        self.save_master_config(config)
        return parameters

    def update_parameter(self, key: str, enabled: bool | None = None, value: Any = None) -> dict[str, Any]:
        config = self.load_master_config()
        parameters = config.get("sections", {}).get("binary", {}).get("parameters", {})
        if key not in parameters:
            parameters[key] = {"enabled": False, "value": None, "description": ""}
        if enabled is not None:
            parameters[key]["enabled"] = enabled
        if value is not None:
            parameters[key]["value"] = value
        return self.update_binary_parameters(parameters)

    def get_dns_config(self) -> dict[str, Any]:
        return self.get_section("dns")

    def update_dns_config(self, config_data: dict[str, Any]) -> dict[str, Any]:
        return self.update_section("dns", config_data)

    def get_system_config(self) -> dict[str, Any]:
        return self.get_section("system")

    def update_system_config(self, config_data: dict[str, Any]) -> dict[str, Any]:
        return self.update_section("system", config_data)

    def build_command_args(self) -> list[str]:
        parameters = self.get_binary_parameters()
        args: list[str] = []
        for key, param in parameters.items():
            if param.get("enabled", False):
                flag = param.get("flag")
                if flag:
                    param_type = param.get("type", "string")
                    value = param.get("value")
                    if param_type == "boolean":
                        if value:
                            args.append(flag)
                    elif value is not None and value != "":
                        args.extend([flag, str(value)])
        return args

    def build_command_preview(self, binary_path: str | None = None) -> str:
        if binary_path is None:
            binary_config = self.get_binary_config()
            binary_path = binary_config.get("config", {}).get("binary_path", "cfst")
        args = self.build_command_args()
        return " ".join([binary_path, *args])

    def get_runtime_context(self) -> dict[str, Any]:
        binary_config = self.get_binary_config()
        parameters = self.get_binary_parameters()
        result_file = parameters.get("result_file", {}).get("value", "data/results/latest.csv")
        return {
            "binary_path": binary_config.get("config", {}).get("binary_path", "cfst"),
            "working_directory": binary_config.get("config", {}).get("working_directory", "."),
            "env": binary_config.get("config", {}).get("env", {}),
            "timeout": binary_config.get("config", {}).get("timeout_seconds", 600),
            "command_args": self.build_command_args(),
            "result_file": result_file,
            "parameter_snapshot": {k: {"enabled": v.get("enabled"), "value": v.get("value")} for k, v in parameters.items()},
        }

    def _create_default_config(self) -> dict[str, Any]:
        now = self._now()
        config: dict[str, Any] = {
            "version": "1.0",
            "kind": "master_config",
            "id": "system_master_config",
            "source": "system",
            "timestamps": {
                "created_at": now,
                "updated_at": now,
            },
            "meta": {
                "description": "COITD整体配置文件",
            },
            "sections": {
                "binary": {
                    "name": "COITD测速控制",
                    "description": "CloudflareSpeedTest二进制程序的运行配置",
                    "config": {
                        "binary_path": "cfst",
                        "working_directory": ".",
                        "env": {},
                        "timeout_seconds": 600,
                    },
                    "parameters": {
                        "thread_count": {"enabled": True, "value": 200, "flag": "-n", "type": "number", "min": 1, "max": 1000, "description": "延迟测速线程数"},
                        "test_count": {"enabled": True, "value": 4, "flag": "-t", "type": "number", "min": 1, "max": 100, "description": "延迟测速次数"},
                        "download_count": {"enabled": True, "value": 10, "flag": "-dn", "type": "number", "min": 1, "max": 100, "description": "下载测速数量"},
                        "download_time": {"enabled": False, "value": 10, "flag": "-dt", "type": "number", "min": 1, "max": 60, "description": "下载测速时间"},
                        "port": {"enabled": False, "value": 443, "flag": "-tp", "type": "number", "min": 1, "max": 65535, "description": "测速端口"},
                        "url": {"enabled": False, "value": "", "flag": "-url", "type": "string", "description": "测速地址"},
                        "httping": {"enabled": False, "value": False, "flag": "-httping", "type": "boolean", "description": "HTTP测速模式"},
                        "httping_code": {"enabled": False, "value": "200", "flag": "-httping-code", "type": "string", "description": "有效HTTP状态码"},
                        "cfcolo": {"enabled": False, "value": "", "flag": "-cfcolo", "type": "string", "description": "匹配地区码"},
                        "latency_limit": {"enabled": True, "value": 200, "flag": "-tl", "type": "number", "min": 0, "max": 9999, "description": "平均延迟上限ms"},
                        "latency_lower": {"enabled": False, "value": 0, "flag": "-tll", "type": "number", "min": 0, "max": 9999, "description": "平均延迟下限ms"},
                        "packet_loss_limit": {"enabled": False, "value": 1.0, "flag": "-tlr", "type": "number", "min": 0, "max": 1, "step": 0.01, "description": "丢包率上限"},
                        "speed_limit": {"enabled": False, "value": 0, "flag": "-sl", "type": "number", "min": 0, "max": 1000, "description": "下载速度下限MB/s"},
                        "display_count": {"enabled": False, "value": 10, "flag": "-p", "type": "number", "min": 0, "max": 1000, "description": "显示结果数量"},
                        "ip_file": {"enabled": False, "value": "ip.txt", "flag": "-f", "type": "string", "description": "IP段数据文件路径"},
                        "ip_list": {"enabled": False, "value": "", "flag": "-ip", "type": "string", "description": "指定IP段"},
                        "result_file": {"enabled": True, "value": "data/results/latest.csv", "flag": "-o", "type": "string", "description": "结果输出文件路径"},
                        "disable_download": {"enabled": False, "value": False, "flag": "-dd", "type": "boolean", "description": "禁用下载测速"},
                        "all_ip": {"enabled": False, "value": False, "flag": "-allip", "type": "boolean", "description": "测速全部IP"},
                        "debug": {"enabled": False, "value": False, "flag": "-debug", "type": "boolean", "description": "调试输出模式"},
                    },
                },
                "dns": {
                    "name": "DNS推送配置",
                    "description": "DNS服务商推送相关配置",
                    "general": {
                        "auto_push_enabled": False,
                        "push_after_test": False,
                        "ip_selection_strategy": "top1",
                        "top_n_count": 3,
                    },
                    "aliyun": {
                        "enabled": False,
                        "access_key_id": "",
                        "access_key_secret": "",
                        "domain": "",
                        "record_type": "A",
                        "ttl": 600,
                    },
                    "cloudflare": {
                        "enabled": False,
                        "api_token": "",
                        "zone_id": "",
                        "record_name": "",
                        "record_type": "A",
                        "proxied": False,
                        "ttl": 1,
                    },
                },
                "system": {
                    "name": "系统设置",
                    "description": "系统级别的配置选项",
                    "web": {"host": "0.0.0.0", "port": 8000, "debug": False},
                    "schedule": {"enabled": False, "cron_expression": "0 */6 * * *", "description": "每6小时执行一次"},
                    "logging": {"level": "INFO", "max_log_files": 30, "auto_cleanup": True},
                    "notification": {"enabled": False, "webhook_url": "", "notify_on_success": True, "notify_on_failure": True},
                },
            },
        }
        self.store.write(MASTER_CONFIG_FILE, config)
        return config

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
