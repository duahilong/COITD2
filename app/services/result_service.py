from __future__ import annotations

import csv
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from app.core.json_store import JsonStore
from app.core.paths import RESULT_DIR, ROOT_DIR
from app.schemas.kinds import SCHEMA_KIND_TASK_RESULT


class ResultService:
    def __init__(self, store: JsonStore | None = None) -> None:
        self.store = store or JsonStore()

    def parse_result_file(
        self,
        *,
        task_id: str,
        result_path: str | None,
        command_preview: str | None = None,
        parameter_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        csv_path = self._resolve_path(result_path)
        if csv_path is None or not csv_path.exists() or csv_path.stat().st_size == 0:
            return None

        with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            rows = [self._parse_row(row, index) for index, row in enumerate(reader, start=1)]

        selected_ips = [row for row in rows if row]
        result_doc = {
            "version": "1.0",
            "kind": SCHEMA_KIND_TASK_RESULT,
            "id": task_id,
            "source": "cfst_adapter",
            "timestamps": {
                "created_at": self._now(),
                "updated_at": self._now(),
            },
            "meta": {
                "task_id": task_id,
                "result_path": str(csv_path.relative_to(ROOT_DIR)) if csv_path.is_relative_to(ROOT_DIR) else str(csv_path),
                "command_preview": command_preview,
                "record_count": len(selected_ips),
            },
            "payload": {
                "selected_ips": selected_ips,
                "parameter_snapshot": parameter_snapshot or {},
            },
        }
        self.store.write(self.result_json_path(task_id), result_doc)
        return result_doc

    def result_json_path(self, task_id: str) -> Path:
        return RESULT_DIR / f"{task_id}.json"

    def load_result(self, task_id: str) -> dict[str, Any] | None:
        path = self.result_json_path(task_id)
        if not self.store.exists(path):
            return None
        return self.store.read(path)

    def summarize_result(self, result_doc: dict[str, Any] | None) -> dict[str, Any]:
        selected_ips = (result_doc or {}).get("payload", {}).get("selected_ips", [])
        best = selected_ips[0] if selected_ips else None
        return {
            "record_count": len(selected_ips),
            "best_ip": best,
            "top_ips": selected_ips[:5],
        }

    def _parse_row(self, row: dict[str, str], rank: int) -> dict[str, Any] | None:
        address = self._pick_value(row, ["IP 地址", "IP", "IP地址", "address"])
        if not address:
            return None
        latency_ms = self._to_float(self._pick_value(row, ["平均延迟", "延迟", "Latency", "latency_ms"]))
        speed_mbps = self._to_float(self._pick_value(row, ["下载速度(MB/s)", "下载速度", "Speed", "speed_mbps"]))
        loss_rate = self._to_float(self._pick_value(row, ["丢包率", "Loss", "loss_rate"]))
        region = self._pick_value(row, ["地区码", "地区", "Region", "colo"]) or "N/A"
        sent = self._to_int(self._pick_value(row, ["已发送", "Sent", "sent"]))
        received = self._to_int(self._pick_value(row, ["已接收", "Received", "received"]))
        return {
            "address": address,
            "family": self._ip_family(address),
            "latency_ms": latency_ms,
            "speed_mbps": speed_mbps,
            "loss_rate": loss_rate,
            "region": region,
            "rank": rank,
            "sent": sent,
            "received": received,
        }

    def _pick_value(self, row: dict[str, str], keys: list[str]) -> str:
        normalized = {self._normalize_key(key): (value or "").strip() for key, value in row.items() if key}
        for key in keys:
            value = normalized.get(self._normalize_key(key), "")
            if value:
                return value
        return ""

    def _normalize_key(self, key: str) -> str:
        return key.strip().replace(" ", "")

    def _to_float(self, value: str) -> float:
        cleaned = value.replace("%", "").replace("MB/s", "").strip()
        if not cleaned:
            return 0.0
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def _to_int(self, value: str) -> int:
        if not value:
            return 0
        try:
            return int(float(value))
        except ValueError:
            return 0

    def _ip_family(self, address: str) -> str:
        try:
            return f"ipv{ip_address(address).version}"
        except ValueError:
            return "unknown"

    def _resolve_path(self, path_value: str | None) -> Path | None:
        if not path_value:
            return None
        path = Path(path_value)
        if path.is_absolute():
            return path
        return (ROOT_DIR / path).resolve()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
