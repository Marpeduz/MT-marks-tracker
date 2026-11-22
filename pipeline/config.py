from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"
ASSETS_DIR = ROOT / "assets"
ICONS_SPRITE_PATH = ASSETS_DIR / "icons.svg"

VEHICLES_PATH = DATA_DIR / "vehicles.json"
LATEST_PATH = DATA_DIR / "latest.json"
META_PATH = DATA_DIR / "meta.json"

VEHICLES_URL = "https://poliroid.me/gunmarks/api/v2/vehicles/ru/ru"
MARKS_URL = "https://poliroid.me/gunmarks/api/v2/data/ru/vehicles/65,85,95,100"

MIN_TIER = 5
MAX_TIER = 11
MARK_KEYS = ("65", "85", "95", "100")

# Абсолютный минимум техники и доля от справочника, ниже которой снимок бракуются
MIN_VEHICLES = 400
MIN_POOL_RATIO = 0.95

# Падение секции (уровень / класс / нация) больше чем на 20% считается аномалией
MAX_SECTION_DROP = 0.20
MIN_SECTION_SIZE_FOR_CHECK = 5

MAX_MARK = 50_000
SPIKE_ABS = 300
SPIKE_REL = 0.15

HISTORY_DAYS = 365
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MT-marks-tracker/1.0"
DEFAULT_ICONS_URL = "https://cdn.poliroid.me/icons/tanks_svg/ru"
