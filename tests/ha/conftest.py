"""Run Home Assistant integration tests against the repository's local component."""

from pathlib import Path
import shutil

import pytest


DOMAIN = "resource_queue_manager"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir: str) -> str:
    """Install the custom component in an isolated HA test configuration."""
    destination = Path(hass_tmp_config_dir) / "custom_components" / DOMAIN
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PROJECT_ROOT / "custom_components" / DOMAIN, destination)
    return hass_tmp_config_dir
