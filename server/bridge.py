from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Bridge:
    def __init__(self, bridge_dir: str) -> None:
        self.root = Path(bridge_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.intent_path = self.root / "intent.json"
        self.status_path = self.root / "status.json"
        self.fills_path = self.root / "fills.json"

    def write_intent(self, payload: dict[str, Any]) -> None:
        self.intent_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def read_status(self) -> dict[str, Any]:
        if not self.status_path.exists():
            return {}
        return json.loads(self.status_path.read_text(encoding="utf-8"))

    def read_fills(self) -> list[dict[str, Any]]:
        if not self.fills_path.exists():
            return []
        raw = json.loads(self.fills_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
