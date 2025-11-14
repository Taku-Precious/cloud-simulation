"""
Logging Utility
Professional logging setup with file and console handlers
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional
import sys


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }

    def format(self, record):
        # Add color to level name
        if record.levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[record.levelname]}"
                f"{record.levelname}"
                f"{self.COLORS['RESET']}"
            )
        return super().format(record)


def setup_logging(
    log_level: str = "INFO",
    log_to_file: bool = True,
    log_to_console: bool = True,
    log_file_path: str = "logs/cloudsim.log",
    max_log_file_size: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    format_type: str = "detailed"
) -> logging.Logger:
    """
    Setup logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Enable file logging
        log_to_console: Enable console logging
        log_file_path: Path to log file
        max_log_file_size: Maximum size of log file before rotation
        backup_count: Number of backup log files to keep
        format_type: Format type (simple, detailed, json)
    
    Returns:
        Configured logger instance
    """
    
    # Create logger
    logger = logging.getLogger("CloudSim")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Define formats
    if format_type == "simple":
        log_format = "%(levelname)s - %(message)s"
    elif format_type == "json":
        log_format = '{"time":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","message":"%(message)s"}'
    else:  # detailed
        log_format = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        
        # Use colored formatter for console
        console_formatter = ColoredFormatter(log_format, datefmt=date_format)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # File handler
    if log_to_file:
        # Create logs directory if it doesn't exist
        try:
            log_dir = os.path.dirname(log_file_path) if os.path.dirname(log_file_path) else "."
            if log_dir != "." and not os.path.exists(log_dir):
                # Use Path for better Windows compatibility
                from pathlib import Path
                Path(log_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            # If directory creation fails, log to current directory
            log_file_path = os.path.basename(log_file_path)

        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=max_log_file_size,
            backupCount=backup_count
        )
        file_handler.setLevel(getattr(logging, log_level.upper()))
        
        # Use standard formatter for file (no colors)
        file_formatter = logging.Formatter(log_format, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    logger.info(f"Logging initialized - Level: {log_level}, File: {log_to_file}, Console: {log_to_console}")
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(f"CloudSim.{name}")


# Example usage
if __name__ == "__main__":
    # Setup logging
    logger = setup_logging(
        log_level="DEBUG",
        log_to_file=True,
        log_to_console=True,
        format_type="detailed"
    )
    
    # Test logging
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")
    
    # Module-specific logger
    module_logger = get_logger("test_module")
    module_logger.info("This is from a specific module")

