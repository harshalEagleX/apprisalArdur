"""
Apprisal OCR Service — Entry Point

Day 2 scaffold: minimal FastAPI app, schema loaded at startup.
API endpoints added incrementally as each layer is built.
"""

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Bootstrap logging before importing app modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from app.core.schema import schema_loader

app = FastAPI(
    title="Apprisal OCR Service",
    description="Adaptive document extraction platform — 30-day re-engineering",
    version="0.1.0",
)


@app.on_event("startup")
async def startup():
    logging.getLogger(__name__).info(
        "Schema loaded: version=%s, fields=%d",
        schema_loader.schema_version,
        len(schema_loader.all_fields()),
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "schema_version": schema_loader.schema_version,
        "field_count": len(schema_loader.all_fields()),
    }


@app.post("/schema/reload")
async def reload_schema():
    schema_loader.reload()
    return {"reloaded": True, "field_count": len(schema_loader.all_fields())}


@app.get("/schema/fields")
async def list_fields(section: str = None):
    if section:
        fields = schema_loader.fields_for_section(section)
    else:
        fields = schema_loader.all_fields()
    return [
        {
            "canonical_name": f.canonical_name,
            "data_type": f.data_type,
            "required": f.required,
            "sections": f.sections,
            "source_authority": f.source_authority,
            "synonym_count": len(f.synonyms),
            "required_for_review": f.required_for_review,
        }
        for f in fields
    ]
