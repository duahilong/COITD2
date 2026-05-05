from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from app.core.json_store import JsonStore
from app.core.paths import LOG_DIR, ROOT_DIR, RUN_DIR
from app.schemas.files import BINARY_STATE_FILE
from app.schemas.kinds import SCHEMA_KIND_TASK_RUN
from app.services.config_service import ConfigService
from app.services.result_service import ResultService


class BinaryControlService:
    def __init__(
        self,
        store: JsonStore | None = None,
        config_service: ConfigService | None = None,
        result_service: ResultService | None = None,
    ) -> None:
        self.store = store or JsonStore()
        self.config_service = config_service or ConfigService(store=self.store)
        self.result_service = result_service or ResultService(store=self.store)
        self.process: subprocess.Popen[str] | None = None
        self.stdout_handle: TextIO | None = None
        self.stderr_handle: TextIO | None = None
        self.current_task_file: Path | None = None

    def get_runtime_config(self) -> dict[str, Any]:
        binary_config = self.config_service.get_binary_config()
        config_section = binary_config.get("config", {})
        return {
            "version": "1.0",
            "kind": "runtime_config",
            "id": "runtime_from_master",
            "source": "master_config",
            "timestamps": {},
            "meta": {},
            "payload": {
                "binary_path": config_section.get("binary_path", "cfst"),
                "working_directory": config_section.get("working_directory", "."),
                "env": config_section.get("env", {}),
                "timeout_seconds": config_section.get("timeout_seconds", 600),
            },
        }

    def get_state(self) -> dict[str, Any]:
        state = self._read_state()
        self._refresh_process_state(state)
        return state

    def start(self) -> dict[str, Any]:
        state = self.get_state()
        if self._is_running():
            state["last_error"] = "COITD测速程序已经在运行中"
            self._write_state(state)
            return state

        runtime = self.get_runtime_config()
        runtime_payload = runtime["payload"]
        parameter_context = self.config_service.get_runtime_context()
        binary_path = str(runtime_payload.get("binary_path", "cfst"))
        working_directory = Path(runtime_payload.get("working_directory", "."))
        if not working_directory.is_absolute():
            working_directory = ROOT_DIR / working_directory
        executable = self._resolve_executable(binary_path, working_directory)
        command_preview = self._build_command_preview(binary_path, parameter_context["command_args"])

        if executable is None:
            state = self._build_state(
                task_id=state.get("task_id") or "未启动",
                status="error",
                trigger_source="manual",
                pid=None,
                started_at=None,
                finished_at=None,
                stdout_path=None,
                stderr_path=None,
                result_path=parameter_context["result_file"],
                parameter_snapshot=parameter_context["parameter_snapshot"],
                binary_path=binary_path,
                command_preview=command_preview,
                working_directory=str(working_directory),
                last_error=f"未找到可执行文件: {binary_path}",
            )
            self._write_state(state)
            return state

        task_id = self._task_id()
        started_at = self._now()
        stdout_path = LOG_DIR / f"{task_id}.stdout.log"
        stderr_path = LOG_DIR / f"{task_id}.stderr.log"
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        command = self._build_command(executable, parameter_context["command_args"])

        self.stdout_handle = stdout_path.open("w", encoding="utf-8")
        self.stderr_handle = stderr_path.open("w", encoding="utf-8")
        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in runtime_payload.get("env", {}).items()})
        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(working_directory),
                stdout=self.stdout_handle,
                stderr=self.stderr_handle,
                text=True,
                env=env,
            )
        except Exception as exc:
            self._close_log_handles()
            self.process = None
            state = self._build_state(
                task_id=task_id,
                status="error",
                trigger_source="manual",
                pid=None,
                started_at=started_at,
                finished_at=self._now(),
                stdout_path=str(stdout_path.relative_to(ROOT_DIR)),
                stderr_path=str(stderr_path.relative_to(ROOT_DIR)),
                result_path=parameter_context["result_file"],
                parameter_snapshot=parameter_context["parameter_snapshot"],
                binary_path=binary_path,
                command_preview=command_preview,
                working_directory=str(working_directory),
                last_error=str(exc),
            )
            self._write_state(state)
            self._write_run_file(task_id, state)
            return state

        state = self._build_state(
            task_id=task_id,
            status="running",
            trigger_source="manual",
            pid=self.process.pid,
            started_at=started_at,
            finished_at=None,
            stdout_path=str(stdout_path.relative_to(ROOT_DIR)),
            stderr_path=str(stderr_path.relative_to(ROOT_DIR)),
            result_path=parameter_context["result_file"],
            parameter_snapshot=parameter_context["parameter_snapshot"],
            binary_path=binary_path,
            command_preview=command_preview,
            working_directory=str(working_directory),
            last_error=None,
        )
        self._write_state(state)
        self.current_task_file = RUN_DIR / f"{task_id}.json"
        self._write_run_file(task_id, state)
        return state

    def stop(self) -> dict[str, Any]:
        state = self.get_state()
        if not self._is_running() or self.process is None:
            state["last_error"] = "当前没有运行中的COITD测速程序"
            if state.get("status") == "running":
                state["status"] = "stopped"
                state["finished_at"] = self._now()
            self._write_state(state)
            return state

        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        state["status"] = "stopped"
        state["finished_at"] = self._now()
        state["pid"] = None
        state["last_error"] = None
        self._close_log_handles()
        self._finalize_result(state)
        self._write_state(state)
        self._write_run_file(str(state["task_id"]), state)
        self.process = None
        return state

    def restart(self) -> dict[str, Any]:
        if self._is_running():
            self.stop()
        return self.start()

    def latest_result_summary(self) -> dict[str, Any]:
        state = self.get_state()
        task_id = state.get("task_id")
        if not task_id:
            return self.result_service.summarize_result(None)
        result_file = self.result_service.result_json_path(task_id)
        if not self.store.exists(result_file):
            return self.result_service.summarize_result(None)
        return self.result_service.summarize_result(self.store.read(result_file))

    def _read_state(self) -> dict[str, Any]:
        if self.store.exists(BINARY_STATE_FILE):
            existing_state = self.store.read(BINARY_STATE_FILE)
            if "task_id" in existing_state:
                return existing_state
        runtime = self.get_runtime_config()
        parameter_context = self.config_service.get_runtime_context()
        state = self._build_state(
            task_id="未启动",
            status="idle",
            trigger_source="manual",
            pid=None,
            started_at=None,
            finished_at=None,
            stdout_path=None,
            stderr_path=None,
            result_path=parameter_context["result_file"],
            parameter_snapshot=parameter_context["parameter_snapshot"],
            binary_path=str(runtime["payload"].get("binary_path", "cfst")),
            command_preview=self._build_command_preview(str(runtime["payload"].get("binary_path", "cfst")), parameter_context["command_args"]),
            working_directory=str(runtime["payload"].get("working_directory", ".")),
            last_error=None,
        )
        self._write_state(state)
        return state

    def _write_state(self, state: dict[str, Any]) -> None:
        self.store.write(BINARY_STATE_FILE, state)

    def _refresh_process_state(self, state: dict[str, Any]) -> None:
        if self.process is None:
            return
        return_code = self.process.poll()
        if return_code is None:
            return
        state["pid"] = None
        state["finished_at"] = state.get("finished_at") or self._now()
        state["status"] = "success" if return_code == 0 else "failed"
        state["last_error"] = None if return_code == 0 else f"进程退出码: {return_code}"
        self._close_log_handles()
        self._finalize_result(state)
        self._write_state(state)
        if state.get("task_id"):
            self._write_run_file(str(state["task_id"]), state)
        self.process = None

    def _finalize_result(self, state: dict[str, Any]) -> None:
        task_id = state.get("task_id")
        if not task_id or task_id == "未启动":
            return
        result_doc = self.result_service.parse_result_file(
            task_id=task_id,
            result_path=state.get("result_path"),
            command_preview=state.get("command_preview"),
            parameter_snapshot=state.get("parameter_snapshot"),
        )
        if result_doc:
            state["result_summary"] = self.result_service.summarize_result(result_doc)

    def _write_run_file(self, task_id: str, state: dict[str, Any]) -> None:
        task_file = self.current_task_file or RUN_DIR / f"{task_id}.json"
        task_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": state["status"],
            "trigger_source": state["trigger_source"],
            "pid": state["pid"],
            "started_at": state["started_at"],
            "finished_at": state["finished_at"],
            "stdout_path": state["stdout_path"],
            "stderr_path": state["stderr_path"],
            "result_path": state["result_path"],
            "parameter_snapshot": state["parameter_snapshot"],
        }
        self.store.write(
            task_file,
            {
                "version": "1.0",
                "kind": SCHEMA_KIND_TASK_RUN,
                "id": task_id,
                "source": "web_console",
                "timestamps": {
                    "created_at": state["started_at"] or self._now(),
                    "updated_at": self._now(),
                },
                "meta": {
                    "binary_path": state["binary_path"],
                    "command_preview": state["command_preview"],
                    "working_directory": state["working_directory"],
                    "last_error": state["last_error"],
                },
                "payload": payload,
            },
        )

    def _build_state(
        self,
        *,
        task_id: str,
        status: str,
        trigger_source: str,
        pid: int | None,
        started_at: str | None,
        finished_at: str | None,
        stdout_path: str | None,
        stderr_path: str | None,
        result_path: str | None,
        parameter_snapshot: dict[str, Any],
        binary_path: str,
        command_preview: str,
        working_directory: str,
        last_error: str | None,
    ) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "status": status,
            "trigger_source": trigger_source,
            "pid": pid,
            "started_at": started_at,
            "finished_at": finished_at,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "result_path": result_path,
            "parameter_snapshot": parameter_snapshot,
            "binary_path": binary_path,
            "command_preview": command_preview,
            "working_directory": working_directory,
            "last_error": last_error,
            "result_summary": {"record_count": 0, "best_ip": None, "top_ips": []},
        }

    def _resolve_executable(self, binary_path: str, working_directory: Path) -> Path | None:
        candidate = Path(binary_path)
        if candidate.is_absolute() and candidate.exists():
            return candidate
        if candidate.exists():
            return candidate.resolve()
        relative_candidate = (working_directory / candidate).resolve()
        if relative_candidate.exists():
            return relative_candidate
        resolved = shutil.which(binary_path)
        return Path(resolved) if resolved else None

    def _build_command(self, executable: Path, command_args: list[str]) -> list[str]:
        if executable.suffix.lower() == ".py":
            return [sys.executable, str(executable), *command_args]
        return [str(executable), *command_args]

    def _close_log_handles(self) -> None:
        if self.stdout_handle and not self.stdout_handle.closed:
            self.stdout_handle.close()
        if self.stderr_handle and not self.stderr_handle.closed:
            self.stderr_handle.close()
        self.stdout_handle = None
        self.stderr_handle = None

    def _is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _build_command_preview(self, binary_path: str, command_args: list[str]) -> str:
        return " ".join([binary_path, *command_args])

    def _task_id(self) -> str:
        return datetime.now().strftime("task_%Y%m%d_%H%M%S")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
