"""
Complete Integration Test: Authentication + File Storage
Tests full workflow: register -> login -> OTP -> storage operations
"""

import sys
import time
from pathlib import Path

# Add project root to path
_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Add auth directory to path for protobuf files
_auth_dir = _project_root / "auth"
if str(_auth_dir) not in sys.path:
    sys.path.insert(0, str(_auth_dir))

import cloudsecurity_pb2
from auth.client import CloudSecurityClient
from integration.storage_manager import STORAGE_BASE_DIR


def test_complete_auth_flow():
    """Test complete authentication flow with OTP"""
    print("\n" + "=" * 70)
    print("TEST: Complete Authentication Flow")
    print("=" * 70)
    
    try:
        # Create client
        client = CloudSecurityClient()
        if not client.connect():
            print("❌ Failed to connect to server")
            return False, None
        
        print("✓ Connected to server")
        
        # Register new user
        username = "authtest001"
        email = "authtest001@example.com"
        password = "TestPass123!"
        
        print(f"\n[1] Registering user: {username}")
        response = client.stub.login(
            cloudsecurity_pb2.Request(
                login="__REGISTER__",
                password=f"REGISTER|{username}|{email}|{password}"
            )
        )
        
        if "REG_SUCCESS" in response.result or "already exists" in response.result:
            print(f"✓ Registration handled: {response.result[:60]}...")
        else:
            print(f"❌ Registration failed: {response.result}")
            client.disconnect()
            return False, None
        
        # Login
        print(f"\n[2] Logging in: {username}")
        success, message, session_id = client.login(username, password)
        
        if not success:
            print(f"❌ Login failed: {message}")
            client.disconnect()
            return False, None
        
        print(f"✓ Login successful")
        print(f"  Session ID: {session_id[:32]}...")
        print(f"  Message: {message}")
        
        # Extract OTP from session if available
        # In production, OTP would be sent via email
        # For testing, we get it from the database
        print(f"\n[3] Getting OTP from database for testing...")
        from auth.database import get_database
        auth_db = get_database()
        session = auth_db.get_session(session_id)
        
        if not session:
            print(f"❌ Session not found in database")
            client.disconnect()
            return False, None
        
        otp = session['otp']
        print(f"✓ OTP retrieved: {otp}")
        
        # Verify OTP
        print(f"\n[4] Verifying OTP...")
        response = client.stub.login(
            cloudsecurity_pb2.Request(
                login="__OTP_VERIFY__",
                password=f"OTP_VERIFY|{username}|{session_id}|{otp}"
            )
        )
        
        if "AUTH_SUCCESS" in response.result:
            parts = response.result.split("|")
            if len(parts) >= 2:
                auth_token = parts[1]
                print(f"✓ OTP verification successful!")
                print(f"  Auth Token: {auth_token[:32]}...")
                client.disconnect()
                return True, auth_token
            else:
                print(f"❌ Invalid OTP response format: {response.result}")
                client.disconnect()
                return False, None
        else:
            print(f"❌ OTP verification failed: {response.result}")
            client.disconnect()
            return False, None
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_file_operations_with_auth(auth_token: str):
    """Test file operations using valid auth token"""
    print("\n" + "=" * 70)
    print("TEST: File Operations with Authentication")
    print("=" * 70)
    
    try:
        from integration.storage_manager import get_storage_manager
        
        manager = get_storage_manager()
        
        # Test 1: Upload file
        print("\n[1] Testing file upload...")
        test_filename = "test_document.txt"
        test_content = b"This is test file content for storage operations testing."
        
        success, message, file_id = manager.upload_file(
            auth_token, 
            test_filename, 
            test_content
        )
        
        if success:
            print(f"✓ File uploaded successfully")
            print(f"  File ID: {file_id}")
            print(f"  Message: {message}")
        else:
            print(f"❌ Upload failed: {message}")
            return False
        
        # Test 2: Download file
        print("\n[2] Testing file download...")
        success, message, file_data = manager.download_file(auth_token, file_id)
        
        if success:
            print(f"✓ File downloaded successfully")
            print(f"  Downloaded size: {len(file_data)} bytes")
            print(f"  Content matches: {file_data == test_content}")
            if file_data != test_content:
                print(f"❌ Downloaded content doesn't match original!")
                return False
        else:
            print(f"❌ Download failed: {message}")
            return False
        
        # Test 3: List files
        print("\n[3] Testing list user files...")
        success, message, files = manager.list_user_files(auth_token)
        
        if success:
            print(f"✓ Files listed successfully")
            print(f"  Total files: {len(files)}")
            for f in files:
                print(f"    - {f['filename']} ({f['file_size']} bytes)")
        else:
            print(f"❌ List failed: {message}")
            return False
        
        # Test 4: Get quota
        print("\n[4] Testing quota retrieval...")
        success, message, quota = manager.get_user_quota(auth_token)
        
        if success:
            print(f"✓ Quota retrieved successfully")
            quota_gb = quota['quota_bytes'] / (1024**3)
            used_gb = quota['used_bytes'] / (1024**3)
            available_gb = (quota['quota_bytes'] - quota['used_bytes']) / (1024**3)
            print(f"  Total quota: {quota_gb:.2f} GB")
            print(f"  Used: {used_gb:.6f} GB")
            print(f"  Available: {available_gb:.2f} GB")
        else:
            print(f"❌ Quota retrieval failed: {message}")
            return False
        
        # Test 5: Delete file
        print("\n[5] Testing file deletion...")
        success, message = manager.delete_file(auth_token, file_id)
        
        if success:
            print(f"✓ File deleted successfully")
            print(f"  Message: {message}")
        else:
            print(f"❌ Delete failed: {message}")
            return False
        
        # Test 6: Verify file is deleted
        print("\n[6] Verifying file is deleted...")
        success, message, file_data = manager.download_file(auth_token, file_id)
        
        if not success and "deleted" in message.lower():
            print(f"✓ File properly marked as deleted")
            print(f"  Message: {message}")
        elif not success:
            print(f"✓ File cannot be downloaded (deleted)")
        else:
            print(f"❌ File should not be downloadable after deletion!")
            return False
        
        print("\n✓ All file operations passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("COMPLETE INTEGRATION TEST")
    print("Authentication + File Storage Operations")
    print("=" * 70)
    
    try:
        # Test 1: Authentication
        auth_passed, auth_token = test_complete_auth_flow()
        
        if not auth_passed or not auth_token:
            print("\n❌ Authentication test failed - cannot proceed with storage tests")
            sys.exit(1)
        
        # Test 2: File operations with valid auth
        storage_passed = test_file_operations_with_auth(auth_token)
        
        # Summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        print(f"Authentication Test:     {'✓ PASSED' if auth_passed else '❌ FAILED'}")
        print(f"File Storage Test:       {'✓ PASSED' if storage_passed else '❌ FAILED'}")
        print("=" * 70)
        
        if auth_passed and storage_passed:
            print("\n✓✓✓ COMPLETE INTEGRATION TEST PASSED! ✓✓✓")
            print("\nSystem is fully functional:")
            print("  ✓ User registration working")
            print("  ✓ OTP authentication working")
            print("  ✓ Token generation working")
            print("  ✓ File upload working (disk-based)")
            print("  ✓ File download working with integrity check")
            print("  ✓ File listing working")
            print("  ✓ Quota tracking working")
            print("  ✓ File deletion working")
            print(f"\nFiles stored at: {STORAGE_BASE_DIR}")
            sys.exit(0)
        else:
            print("\n❌ Some tests failed")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
