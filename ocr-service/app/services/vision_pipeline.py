"""Optional LLaVA scene-understanding pipeline.

Moondream remains the checkbox fallback. This module is for condition,
occupancy, obsolescence, and room-type evidence when a LLaVA model is selected
through Ollama.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, Optional

from app.services.ollama_service import analyze_photo_llava, is_llava_available


@dataclass
class VisionResult:
    page: int
    task: str
    response: str


CONDITION_PROMPT = (
    "Based on this appraisal photo, estimate property condition on a C1-C6 scale. "
    "C1 is new, C6 is severely damaged. Respond with JSON keys rating and justification."
)
OCCUPANCY_PROMPT = (
    "Does this interior appraisal photo show signs of occupancy such as furniture, personal items, or active use? "
    "Respond with JSON keys occupancy (occupied/vacant/staged) and observations."
)
ROOM_PROMPT = (
    "Identify the room/photo type. Options: kitchen, living room, dining room, bedroom, bathroom, basement, attic, "
    "crawl space, exterior front, exterior rear, garage, outbuilding, street scene. Respond with one option and reason."
)
OBSOLESCENCE_PROMPT = (
    "Does this street/aerial/exterior appraisal photo show power lines, commercial buildings, industrial facilities, "
    "railroad tracks, or heavy traffic road near the property? List observed items only."
)


async def analyze_pages(page_images: Dict[int, object], max_pages: int = 8) -> list[VisionResult]:
    if not page_images or not is_llava_available():
        return []
    tasks = []
    for page, image in sorted(page_images.items())[:max_pages]:
        tasks.extend([
            (page, "condition", analyze_photo_llava(image, CONDITION_PROMPT)),
            (page, "occupancy", analyze_photo_llava(image, OCCUPANCY_PROMPT)),
            (page, "room_type", analyze_photo_llava(image, ROOM_PROMPT)),
            (page, "obsolescence", analyze_photo_llava(image, OBSOLESCENCE_PROMPT)),
        ])
    responses = await asyncio.gather(*(task for _, _, task in tasks))
    return [
        VisionResult(page=page, task=task_name, response=response)
        for (page, task_name, _), response in zip(tasks, responses)
        if response
    ]


def analyze_pages_sync(page_images: Dict[int, object], max_pages: int = 8) -> list[VisionResult]:
    try:
        return asyncio.run(analyze_pages(page_images, max_pages=max_pages))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(analyze_pages(page_images, max_pages=max_pages))
        finally:
            loop.close()
