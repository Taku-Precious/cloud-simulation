"""Quick API test without requirements on running servers"""
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("\n[TEST] Validating FastAPI wrapper code structure...")

try:
    logger.info("Importing fastapi_wrapper...")
    import fastapi_wrapper
    
    logger.info("✓ FastAPI wrapper imported successfully")
    logger.info(f"✓ App object: {fastapi_wrapper.app}")
    logger.info(f"✓ Number of routes: {len(fastapi_wrapper.app.routes)}")
    
    # Check for all required endpoints
    routes = {route.path: route.methods for route in fastapi_wrapper.app.routes if hasattr(route, 'methods')}
    
    required_endpoints = {
        '/health': {'GET'},
        '/api/version': {'GET'},
        '/auth/register': {'POST'},
        '/auth/login': {'POST'},
        '/auth/verify-otp': {'POST'},
        '/storage/upload': {'POST'},
        '/storage/download/{file_id}': {'GET'},
        '/storage/{file_id}': {'DELETE'},
        '/storage/list': {'GET'},
        '/storage/quota': {'GET'},
    }
    
    logger.info("\nChecking endpoints:")
    all_present = True
    for endpoint, methods in required_endpoints.items():
        if endpoint in routes:
            route_methods = routes[endpoint] - {'OPTIONS', 'HEAD'}
            if methods.issubset(route_methods):
                logger.info(f"  ✓ {endpoint} -> {methods}")
            else:
                logger.warning(f"  ⚠ {endpoint} -> Expected {methods}, got {route_methods}")
                all_present = False
        else:
            logger.warning(f"  ✗ {endpoint} NOT FOUND")
            all_present = False
    
    if all_present:
        print("\n✓ All required endpoints are present!")
        print("\n✓ FastAPI wrapper is structurally valid")
        print("\n✓ Next: Start gRPC server and FastAPI wrapper, then run tests")
        sys.exit(0)
    else:
        print("\n⚠ Some endpoints are missing or incorrect")
        sys.exit(1)

except Exception as e:
    logger.error(f"✗ Error: {e}", exc_info=True)
    sys.exit(1)
