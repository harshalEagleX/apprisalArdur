"""Single-call probe: how does the configured vision model behave on ONE page?

Isolates model/latency/format behaviour from the full pipeline, so a slow or
failing run can be diagnosed in seconds instead of by re-running 27 calls.

Usage:
    PYTHONPATH=. python 3.6/probe_one.py [page] [n_images] [dpi]
"""
from __future__ import annotations

import json
import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

PDF = "3.6/Email - AppraisalArdur - Outlook (1).pdf"


def main() -> int:
    page = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    n_images = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 130

    from app.extraction.vision.provider import get_vision_provider
    from app.extraction.vision.render import render_page

    provider = get_vision_provider()
    if provider is None:
        print("no vision provider configured")
        return 1
    print(f"provider={provider.name} model={provider.model}")

    images = []
    for i in range(n_images):
        img = render_page(PDF, page + i, dpi=dpi)
        if img:
            images.append(img)
    print(f"{len(images)} image(s) at {dpi} DPI, "
          f"{images[0].width}x{images[0].height}px, "
          f"~{sum(i.tokens for i in images):,} image tokens")

    schema = {
        "type": "object", "additionalProperties": False,
        "required": ["headings", "any_text_visible"],
        "properties": {
            "headings": {"type": "array", "items": {"type": "string"},
                         "description": "Section headings printed on the page."},
            "any_text_visible": {"type": "boolean",
                                 "description": "Whether any printed text is legible."},
        },
    }

    t0 = time.time()
    resp = provider.transcribe(
        images,
        "List the section headings printed on this page of an appraisal report.",
        schema, max_tokens=1500, effort="low")
    elapsed = time.time() - t0

    print(f"\nelapsed {elapsed:.1f}s | ok={resp.ok} truncated={resp.truncated}")
    print(f"tokens in={resp.input_tokens} out={resp.output_tokens}")
    if resp.error:
        print(f"ERROR: {resp.error}")
    print(json.dumps(resp.data, indent=1)[:1200])
    return 0 if resp.ok else 1


if __name__ == "__main__":
    sys.exit(main())
