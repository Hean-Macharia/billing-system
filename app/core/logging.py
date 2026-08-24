"""
Structured logging configuration.
"""
import logging
import logging.config
import sys
import os
from datetime import datetime
from typing import Any, Dict

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = datetime.utcnow().isoformat() + "Z"
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["service"] = "isp-billing"
        if "message" not in log_record:
            log_record["message"] = record.getMessage()


def setup_logging(log_level: str = "INFO", environment: str = "development") -> None:
    is_production = environment.lower() == "production"
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            },
            "json": {
                "()": CustomJsonFormatter,
                "format": "%(timestamp)s %(level)s %(name)s %(message)s"
            },
            "detailed": {
                "format": "%(asctime)s [%(levelname)s] %(name)s [%(filename)s:%(lineno)d] %(funcName)s(): %(message)s"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "json" if is_production else "detailed",
                "level": log_level,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": "logs/isp-billing.log",
                "maxBytes": 10485760,
                "backupCount": 10,
                "formatter": "json",
                "level": log_level,
            },
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": "logs/isp-billing-error.log",
                "maxBytes": 10485760,
                "backupCount": 10,
                "formatter": "json",
                "level": "ERROR",
            }
        },
        "loggers": {
            "": {
                "handlers": ["console", "file", "error_file"] if is_production else ["console"],
                "level": log_level,
                "propagate": False
            },
            "uvicorn": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False
            },
            "motor": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False
            },
            "pymongo": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False
            }
        }
    }
    os.makedirs("logs", exist_ok=True)
    logging.config.dictConfig(config)
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured - level={log_level} env={environment}")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)