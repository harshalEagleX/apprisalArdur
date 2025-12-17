import os
import json
import logging
import logging.handlers
from datetime import datetime
from typing import Any, Dict

# Create logs directory
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

class JsonFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings after parsing the LogRecord.
    """
    def __init__(self, fmt_dict: Dict[str, str] = None, datefmt: str = None):
        self.fmt_dict = fmt_dict if fmt_dict is not None else {
            'timestamp': 'asctime',
            'level': 'levelname',
            'logger': 'name',
            'message': 'message'
        }
        self.default_json_handler = None
        self.datefmt = datefmt
        # Initialize the standard formatter to handle date formatting
        super().__init__(fmt=None, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        
        # Prepare the dictionary
        log_record = {}
        
        # Add basic fields
        if "asctime" in self.fmt_dict:
            log_record["timestamp"] = self.formatTime(record, self.datefmt)
        else:
            log_record["timestamp"] = datetime.utcnow().isoformat()
            
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["message"] = record.message
        
        # Add exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        
        # Add stack trace if present
        if record.stack_info:
            log_record["stack_info"] = self.formatStack(record.stack_info)
            
        # Add extra fields from the record (e.g. from extra={...})
        for key, value in record.__dict__.items():
            if key not in ["args", "asctime", "created", "exc_info", "exc_text", "filename",
                          "funcName", "levelname", "levelno", "lineno", "module",
                          "msecs", "message", "msg", "name", "pathname", "process",
                          "processName", "relativeCreated", "stack_info", "thread", "threadName"]:
                log_record[key] = value

        return json.dumps(log_record)

def setup_logging(
    service_name: str = "appraisal_ocr",
    log_level: str = "INFO"
) -> logging.Logger:
    """
    Setup logging configuration with:
    1. Console handler (Human readable)
    2. File handler (JSON, all logs)
    3. Error file handler (JSON, errors only)
    """
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # clear existing handlers
    logger.handlers = []
    
    # 1. Console Handler - Human Readable
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 2. App Log Handler - JSON, Rotating
    app_log_path = os.path.join(LOGS_DIR, "app.log")
    file_handler = logging.handlers.RotatingFileHandler(
        app_log_path, maxBytes=10*1024*1024, backupCount=5  # 10MB, 5 backups
    )
    file_handler.setLevel(log_level)
    json_formatter = JsonFormatter()
    file_handler.setFormatter(json_formatter)
    logger.addHandler(file_handler)
    
    # 3. Error Log Handler - JSON, Rotating (Errors only)
    error_log_path = os.path.join(LOGS_DIR, "error.log")
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_path, maxBytes=10*1024*1024, backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(json_formatter)
    logger.addHandler(error_handler)
    
    # Create specific logger for the application
    app_logger = logging.getLogger(service_name)
    
    return app_logger

# Create a default logger instance
logger = setup_logging()
