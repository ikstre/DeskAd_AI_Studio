from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from ..assets import enabled_asset_ids, load_desk_assets
from ..config import get_settings
from ..library import (
    load_reference_manifest,
    list_library_files,
    model_compatible_extensions,
    shared_library_status,
)


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

router = APIRouter()


def _settings_base_url() -> str:
    return get_settings().public_api_base_url.rstrip("/")


@router.get("/assets/desk")
def list_desk_assets():
    """Return available desk accessories and default selected asset ids."""
    return {"assets": load_desk_assets(), "default_asset_ids": enabled_asset_ids()}


@router.get("/assets/references")
def list_reference_assets():
    return {"references": load_reference_manifest(_settings_base_url())}


@router.get("/models/library")
def list_model_library():
    return {
        "files": list_library_files(_settings_base_url()),
        "model_compatible_extensions": model_compatible_extensions(),
        "shared": shared_library_status(),
    }


@router.get("/layouts")
def list_layouts():
    """Return representative keyboard layout ids from data/layouts."""
    layouts = []
    for path in sorted((DATA_DIR / "layouts").glob("layout_*.json")):
        layout_id = path.stem.replace("layout_", "")
        layouts.append({"id": layout_id, "name": f"{layout_id.upper()} Layout"})
    return {"layouts": layouts}
