from pathlib import Path
import sys
import traceback
from typing import List, Optional
import json
from pydantic import BaseModel, Field


class UserSettings(BaseModel):
    platform: str = sys.platform
    downloaded_models: List[str] = Field(default_factory=list)
    preferred_model: Optional[str] = None
    chrome_path: Optional[str] = None

    def save(self) -> str:
        """save settings to file"""
        settings_dir = Path.home() / ".bro"

        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_file = settings_dir / "user_settings.json"

        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2)

        return str(settings_file)
    
    @classmethod
    def load(cls) -> "UserSettings":
        """load settings from path"""
        settings_file = Path.home() / ".bro" / "user_settings.json"

        if settings_file.exists():
            try:
                with open(settings_file, "r") as f:
                    data = json.load(f)
                return cls(**data)
            except(json.JSONDecodeError, Exception):
                traceback.print_exc()

        return cls()
