from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from ..errors import not_found
from ..plates import get_plate_preview_path, keyboard_layout_repo_path, list_plate_brands, search_plates


router = APIRouter()


@router.get("/plates")
def list_plates(query: str = "", brand: str = "", limit: int = 80):
    """Return keyboard plate catalog items filtered by query and brand."""
    return {
        "repo_path": str(keyboard_layout_repo_path()) if keyboard_layout_repo_path() else None,
        "plates": search_plates(query=query, brand=brand, limit=limit),
    }


@router.get("/plates/brands")
def plate_brands():
    """Return available brands from the plate catalog."""
    return {
        "repo_path": str(keyboard_layout_repo_path()) if keyboard_layout_repo_path() else None,
        "brands": list_plate_brands(),
    }


@router.get("/plates/{plate_id}/preview")
def plate_preview(plate_id: str):
    """Return the selected plate preview image as a static file response."""
    preview_path = get_plate_preview_path(plate_id)
    if preview_path is None or not preview_path.exists():
        raise not_found("Plate preview not found")
    return FileResponse(preview_path)
