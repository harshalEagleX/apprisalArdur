"""
OCR Microservice for Appraisal Document Processing
FastAPI application that extracts fields from appraisal PDFs.
Converted to a proper Modular Monolith architecture.
"""

import time
import uuid
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.logging_config import setup_logging
from app.api.v1.router import api_router

# Setup logging immediately
logger = setup_logging()

app = FastAPI(
    title="Appraisal OCR Service",
    description="Modular Monolith OCR Service for extracting key fields from appraisal PDFs",
    version="2.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    logger.info(
        "Request started",
        extra={
            "method": request.method,
            "path": request.url.path,
            "request_id": request_id,
            "client_host": request.client.host if request.client else None
        }
    )
    
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": process_time_ms,
                "request_id": request_id
            }
        )
        return response
    except Exception as e:
        process_time_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Request failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "error": str(e),
                "duration_ms": process_time_ms,
                "request_id": request_id
            },
            exc_info=True
        )
        raise

# Mount the centralized API router
# We don't prefix the router with API v1 so that the Java client continues to work perfectly against '/'
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
