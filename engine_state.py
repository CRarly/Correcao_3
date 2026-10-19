import json
import os
import time
from datetime import datetime
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent / "engine_state.json"

class EngineStateManager:
    def __init__(self):
        self.reset()

    def reset(self):
        self.is_running = False
        self.should_stop = False
        self.current_stage = "Ocioso"
        self.current_discipline = ""
        self.current_ou = ""
        self.current_activity = ""
        self.current_student = ""
        self.current_mode = "tradicional"
        self.current_item_index = 0
        self.total_items = 0
        self.progress_percent = 0.0
        self.active_plan = None
        self.statistics = {
            "avaliados": 0,
            "auditados": 0,
            "ajustados": 0,
            "plagios_detectados": 0,
            "disciplinas_processadas": 0
        }
        self.logs = []
        self.save()

    def reset_stats(self):
        """Reseta apenas as estatísticas de contagem da execução mantendo o estado geral."""
        self.statistics = {
            "avaliados": 0,
            "auditados": 0,
            "ajustados": 0,
            "plagios_detectados": 0,
            "disciplinas_processadas": 0
        }
        self.progress_percent = 0.0
        self.current_item_index = 0
        self.total_items = 0
        self.save()

    def log(self, message: str, level: str = "INFO"):
        now = datetime.now().strftime("%H:%M:%S")
        log_entry = {
            "timestamp": now,
            "level": level,
            "message": message
        }
        self.logs.append(log_entry)
        # Manter no máximo os últimos 500 logs em memória
        if len(self.logs) > 500:
            self.logs = self.logs[-500:]

        # Imprimir no console também com fallback seguro de encoding
        try:
            print(f"[{now}] [{level}] {message}", flush=True)
        except Exception:
            try:
                import sys
                enc = sys.stdout.encoding or 'ascii'
                safe_msg = message.encode(enc, errors='replace').decode(enc)
                print(f"[{now}] [{level}] {safe_msg}", flush=True)
            except Exception:
                pass
        self.save()

    def update_progress(self, current: int, total: int, student: str = "", activity: str = ""):
        self.current_item_index = current
        self.total_items = total
        if student:
            self.current_student = student
        if activity:
            self.current_activity = activity
        if total > 0:
            self.progress_percent = round((current / total) * 100, 1)
        else:
            self.progress_percent = 0.0
        self.save()

    def set_plan(self, plan: dict):
        self.active_plan = plan
        self.save()

    def request_stop(self):
        self.should_stop = True
        self.log("Parada solicitada pelo usuário.", "WARN")
        self.save()

    def increment_stat(self, stat_name: str, count: int = 1):
        if stat_name in self.statistics:
            self.statistics[stat_name] += count
            self.save()

    def to_dict(self) -> dict:
        return {
            "is_running": self.is_running,
            "should_stop": self.should_stop,
            "current_stage": self.current_stage,
            "current_discipline": self.current_discipline,
            "current_ou": self.current_ou,
            "current_activity": self.current_activity,
            "current_student": self.current_student,
            "current_mode": self.current_mode,
            "current_item_index": self.current_item_index,
            "total_items": self.total_items,
            "progress_percent": self.progress_percent,
            "statistics": self.statistics,
            "active_plan": self.active_plan,
            "logs": self.logs[-100:]  # Últimos 100 logs para a UI
        }

    def save(self):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load(self):
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.is_running = data.get("is_running", False)
                    self.current_stage = data.get("current_stage", "Ocioso")
                    self.current_discipline = data.get("current_discipline", "")
                    self.current_ou = data.get("current_ou", "")
                    self.current_activity = data.get("current_activity", "")
                    self.current_student = data.get("current_student", "")
                    self.current_mode = data.get("current_mode", "tradicional")
                    self.current_item_index = data.get("current_item_index", 0)
                    self.total_items = data.get("total_items", 0)
                    self.progress_percent = data.get("progress_percent", 0.0)
                    self.statistics = data.get("statistics", self.statistics)
                    self.active_plan = data.get("active_plan", None)
                    self.logs = data.get("logs", [])
            except Exception:
                pass

state = EngineStateManager()
