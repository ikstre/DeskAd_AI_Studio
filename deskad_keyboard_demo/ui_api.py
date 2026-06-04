"""Compatibility exports for the Streamlit API helper module.

The implementation lives in ``ui.api_client``. Keep this wrapper so older local
imports of ``ui_api`` continue to work while the UI package split progresses.
"""

from ui.api_client import (
    API_BASE,
    PUBLIC_API_BASE,
    api_get,
    api_post,
    fetch_binary_data_url,
    fetch_text_asset,
    poster_preview_height,
    reference_thumbnail_bytes,
    responsive_svg_document,
    svg_aspect_ratio,
    to_internal_api_url,
)

__all__ = [
    "API_BASE",
    "PUBLIC_API_BASE",
    "api_get",
    "api_post",
    "fetch_binary_data_url",
    "fetch_text_asset",
    "poster_preview_height",
    "reference_thumbnail_bytes",
    "responsive_svg_document",
    "svg_aspect_ratio",
    "to_internal_api_url",
]
