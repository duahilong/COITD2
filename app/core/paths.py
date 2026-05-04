from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = ROOT_DIR / "app"
DATA_DIR = ROOT_DIR / "data"
CONFIG_DIR = DATA_DIR / "configs"
TEMPLATE_DIR = DATA_DIR / "templates"
RUN_DIR = DATA_DIR / "runs"
RESULT_DIR = DATA_DIR / "results"
DATA_LOG_DIR = DATA_DIR / "logs"
PUSH_DIR = DATA_DIR / "pushes"
SCHEDULE_DIR = DATA_DIR / "schedules"
LOG_DIR = ROOT_DIR / "logs"
SCHEMA_DIR = ROOT_DIR / "schemas"
