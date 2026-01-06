#!/usr/bin/env python3
"""
Unified Cloud Service - Startup Script
Starts the unified gRPC server with both authentication and storage capabilities.

Usage:
    python start_unified_server.py

Environment:
    - Configure .env file with authentication and email settings
    - Database files created automatically in project root
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "auth"))
sys.path.insert(0, str(project_root / "integration"))
sys.path.insert(0, str(project_root))

# Import and start server
from integration.unified_server import serve
from config import SERVER_HOST, SERVER_PORT

if __name__ == '__main__':
    print()
    print("=" * 80)
    print("UNIFIED CLOUD SERVICE - Starting")
    print("=" * 80)
    print()
    print(f"Host: {SERVER_HOST}")
    print(f"Port: {SERVER_PORT}")
    print()
    print("Features:")
    print("  ✓ Authentication (login, OTP, registration)")
    print("  ✓ Distributed Storage (upload, download, list, delete, quota)")
    print("  ✓ Token-based access control")
    print("  ✓ User quotas and audit logging")
    print("  ✓ 3x data replication (CloudSim)")
    print()
    print("=" * 80)
    print()
    
    try:
        serve()
    except KeyboardInterrupt:
        print("\nShutdown signal received")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
