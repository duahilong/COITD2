from pathlib import Path
from typing import Any

from app.core.json_store import JsonStore
from app.core.paths import LOG_DIR, PUSH_DIR, RESULT_DIR, RUN_DIR, SCHEDULE_DIR
from app.schemas.files import SAMPLE_LOG_INDEX_FILE, SAMPLE_PUSH_FILE, SAMPLE_RESULT_FILE, SAMPLE_SCHEDULE_FILE, SAMPLE_TASK_FILE
from app.services.binary_control_service import BinaryControlService
from app.services.config_service import ConfigService


class DashboardService:
    def __init__(self, store: JsonStore | None = None, binary_control_service: BinaryControlService | None = None, config_service: ConfigService | None = None) -> None:
        self.store = store or JsonStore()
        self.binary_control_service = binary_control_service or BinaryControlService(store=self.store)
        self.config_service = config_service or ConfigService(store=self.store)

    def _list_json_files(self, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        return sorted(directory.glob("*.json"), reverse=True)

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return self.store.read(path)

    def _read_text(self, path: Path) -> str:
        if not path.exists():
            return "暂无日志"
        content = path.read_text(encoding="utf-8").strip()
        return content or "暂无日志"

    def summary(self) -> dict[str, Any]:
        runs = self._list_json_files(RUN_DIR)
        results = self._list_json_files(RESULT_DIR)
        pushes = self._list_json_files(PUSH_DIR)
        schedules = self._list_json_files(SCHEDULE_DIR)

        run_data = self._read_json(runs[0]) if runs else self._read_json(SAMPLE_TASK_FILE)
        result_data = self._read_json(results[0]) if results else self._read_json(SAMPLE_RESULT_FILE)
        push_data = self._read_json(pushes[0]) if pushes else self._read_json(SAMPLE_PUSH_FILE)
        schedule_data = self._read_json(schedules[0]) if schedules else self._read_json(SAMPLE_SCHEDULE_FILE)
        log_index = self._read_json(SAMPLE_LOG_INDEX_FILE)
        binary_state = self.binary_control_service.get_state()

        stdout_path = self._resolve_log_path(binary_state.get("stdout_path"))
        stderr_path = self._resolve_log_path(binary_state.get("stderr_path"))
        if stdout_path is None or stderr_path is None:
            stdout_path = LOG_DIR / "task_20260504_0001.stdout.log"
            stderr_path = LOG_DIR / "task_20260504_0001.stderr.log"
            if log_index:
                stdout_path = self._resolve_log_path(log_index["payload"].get("stdout_path")) or stdout_path
                stderr_path = self._resolve_log_path(log_index["payload"].get("stderr_path")) or stderr_path

        selected_ips = []
        if result_data:
            selected_ips = result_data["payload"].get("selected_ips", [])

        push_payload = push_data["payload"] if push_data else {}
        run_payload = run_data["payload"] if run_data else {}
        schedule_payload = schedule_data["payload"] if schedule_data else {}

        elapsed_seconds = self._calculate_elapsed(binary_state)

        binary = {
            "task_id": binary_state.get("task_id", run_data["id"] if run_data else "暂无"),
            "status": binary_state.get("status", run_payload.get("status", "unknown")),
            "status_class": self._status_class(binary_state.get("status", run_payload.get("status", "unknown"))),
            "trigger_source": binary_state.get("trigger_source", run_payload.get("trigger_source", "unknown")),
            "pid": binary_state.get("pid", run_payload.get("pid", "暂无")),
            "started_at": binary_state.get("started_at", run_payload.get("started_at", "暂无")),
            "finished_at": binary_state.get("finished_at", run_payload.get("finished_at", "暂无")),
            "schedule_name": schedule_payload.get("schedule_name", "暂无"),
            "schedule_enabled": schedule_payload.get("enabled", False),
            "next_run_at": schedule_payload.get("next_run_at") or "待接入 systemd 时间",
            "selected_ips": selected_ips[:2],
            "binary_path": binary_state.get("binary_path", "cfst"),
            "working_directory": binary_state.get("working_directory", "."),
            "command_preview": binary_state.get("command_preview", "cfst"),
            "last_error": binary_state.get("last_error"),
            "elapsed_seconds": elapsed_seconds,
        }

        return {
            "run_count": len(runs),
            "result_count": len(results),
            "push_count": len(pushes),
            "schedule_count": len(schedules),
            "latest_run": runs[0].name if runs else None,
            "latest_result": results[0].name if results else None,
            "latest_push": pushes[0].name if pushes else None,
            "latest_schedule": schedules[0].name if schedules else None,
            "binary": binary,
            "dns": {
                "providers": {
                    "aliyun": self.config_service.get_dns_config().get("aliyun", {}).get("enabled", False),
                    "cloudflare": self.config_service.get_dns_config().get("cloudflare", {}).get("enabled", False),
                },
                "provider": push_payload.get("provider", "暂无"),
                "zone": push_payload.get("target", {}).get("zone", "暂无"),
                "record_name": push_payload.get("target", {}).get("record_name", "暂无"),
                "record_type": push_payload.get("target", {}).get("record_type", "暂无"),
                "status": push_payload.get("status", "unknown"),
                "latest_push_at": push_payload.get("pushed_at", "暂无"),
                "latest_push_status": push_payload.get("status", "暂无"),
                "latest_push_ip": push_payload.get("selected_ips", [None])[0] if push_payload.get("selected_ips") else "暂无",
                "before_records": push_payload.get("before_records", []),
                "after_records": push_payload.get("after_records", []),
                "selected_ips": push_payload.get("selected_ips", []),
                "message": push_payload.get("response_summary", {}).get("message", "暂无"),
                "request_id": push_payload.get("response_summary", {}).get("request_id", "暂无"),
            },
            "history": {
                "task_id": run_data["id"] if run_data else "暂无",
                "result_id": result_data["id"] if result_data else "暂无",
                "push_id": push_data["id"] if push_data else "暂无",
                "status": run_payload.get("status", "unknown"),
                "result_ip_count": len(selected_ips),
                "latest_files": [
                    runs[0].name if runs else "暂无",
                    results[0].name if results else "暂无",
                    pushes[0].name if pushes else "暂无",
                    schedules[0].name if schedules else "暂无",
                ],
                "runs": self._build_runs_list(runs[:10]),
                "top_ips": selected_ips[:5],
            },
            "logs": {
                "stdout": self._read_text(stdout_path),
                "stderr": self._read_text(stderr_path),
                "highlights": log_index["payload"].get("highlights", []) if log_index else [],
                "lines": self._build_log_lines(self._read_text(stdout_path)),
            },
        }

    def _resolve_log_path(self, path_value: str | None) -> Path | None:
        if not path_value:
            return None
        path = Path(path_value)
        if path.is_absolute():
            return path
        return LOG_DIR.parent / path

    def _build_runs_list(self, run_files: list[Path]) -> list[dict[str, Any]]:
        runs = []
        for run_file in run_files:
            run_data = self._read_json(run_file)
            if run_data:
                payload = run_data.get("payload", {})
                runs.append({
                    "id": run_data.get("id", "未知"),
                    "trigger": payload.get("trigger_source", "未知"),
                    "status": payload.get("status", "未知"),
                    "started_at": payload.get("started_at", "未知"),
                })
        return runs

    def _build_log_lines(self, log_content: str) -> list[dict[str, str]]:
        lines = []
        for line in log_content.split("\n"):
            if line.strip():
                lines.append({"time": "", "text": line})
        return lines[-50:]

    def _calculate_elapsed(self, binary_state: dict[str, Any]) -> str:
        from datetime import datetime, timezone
        started_at = binary_state.get("started_at")
        finished_at = binary_state.get("finished_at")
        if not started_at:
            return "0"
        try:
            start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            if finished_at:
                end_time = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
            else:
                end_time = datetime.now(timezone.utc)
            elapsed = (end_time - start_time).total_seconds()
            return str(int(elapsed))
        except Exception:
            return "0"

    def _status_class(self, status: str) -> str:
        mapping = {
            "idle": "warn",
            "running": "info",
            "success": "success",
            "stopped": "warn",
            "failed": "warn",
            "error": "warn",
        }
        return mapping.get(status, "warn")
