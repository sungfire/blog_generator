import base64
import json
import os
from pathlib import Path


APP_DIR_NAME = "BlogWriter"
CONFIG_FILE_NAME = "config.json"


def get_config_path(base_dir: Path | None = None) -> Path:
    if base_dir is not None:
        return base_dir / CONFIG_FILE_NAME

    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIR_NAME / CONFIG_FILE_NAME
    return Path.home() / ".blog_writer" / CONFIG_FILE_NAME


def load_api_key(config_path: Path | None = None) -> str:
    path = config_path or get_config_path()
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        encoded = data.get("api_key", "")
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8") if encoded else ""
    except Exception:
        return ""


def save_api_key(api_key: str, config_path: Path | None = None) -> None:
    key = api_key.strip()
    if not key:
        return
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = base64.b64encode(key.encode("utf-8")).decode("ascii")
    path.write_text(json.dumps({"api_key": encoded}, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_api_key(config_path: Path | None = None) -> None:
    path = config_path or get_config_path()
    if path.exists():
        path.unlink()
