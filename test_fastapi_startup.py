"""Test FastAPI wrapper startup"""
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    logger.info("Importing FastAPI wrapper...")
    import fastapi_wrapper
    logger.info("✓ FastAPI wrapper imported successfully")
    
    logger.info("Checking app object...")
    app = fastapi_wrapper.app
    logger.info(f"✓ FastAPI app object exists: {app}")
    
    logger.info("Checking routes...")
    routes = [route.path for route in app.routes]
    logger.info(f"✓ Found {len(routes)} routes:")
    for route in sorted(set(routes)):
        logger.info(f"  - {route}")
    
    logger.info("\n✓ FastAPI wrapper is ready for startup!")
    
except Exception as e:
    logger.error(f"✗ Error: {e}", exc_info=True)
    sys.exit(1)
