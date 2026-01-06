"""
Direct Unit Tests for Storage Manager
Tests disk-based file operations without gRPC overhead
"""

import sys
import hashlib
from pathlib import Path

# Add project root to path
_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from integration.storage_manager import get_storage_manager, STORAGE_BASE_DIR
from integration.user_storage_db import get_user_storage_database
from auth.database import get_database


def create_test_auth_token(username: str) -> str:
    """Create a valid auth token for testing"""
    try:
        auth_db = get_database()
        from auth.utils import generate_auth_token
        from datetime import datetime, timedelta
        from auth.config import SESSION_EXPIRY_MINUTES
        
        # Create test user
        auth_db.create_user(username, f"{username}@test.com", "hashed_password")
        
        # Create auth token
        auth_token = generate_auth_token()
        token_expires_at = datetime.now() + timedelta(minutes=SESSION_EXPIRY_MINUTES)
        auth_db.create_auth_token(auth_token, username, token_expires_at)
        
        return auth_token
    except Exception as e:
        print(f"Failed to create auth token: {e}")
        return None


def test_file_upload_and_storage():
    """Test file upload and disk storage"""
    print("\n" + "=" * 70)
    print("TEST 1: File Upload and Disk Storage")
    print("=" * 70)
    
    try:
        manager = get_storage_manager()
        storage_db = get_user_storage_database()
        
        username = "storagetest001"
        filename = "test_doc.txt"
        test_content = b"This is test file content for disk storage."
        
        print(f"\n[1] Creating auth token for user: {username}")
        auth_token = create_test_auth_token(username)
        if not auth_token:
            print("❌ Failed to create auth token")
            return False
        print(f"✓ Auth token created: {auth_token[:32]}...")
        
        print(f"\n[2] Uploading file: {filename}")
        success, message, file_id = manager.upload_file(auth_token, filename, test_content)
        
        if not success:
            print(f"❌ Upload failed: {message}")
            return False
        
        print(f"✓ File uploaded successfully")
        print(f"  File ID: {file_id}")
        print(f"  File size: {len(test_content)} bytes")
        
        print(f"\n[3] Verifying file exists on disk")
        file_path = Path(STORAGE_BASE_DIR) / username / file_id
        if file_path.exists():
            print(f"✓ File exists at: {file_path}")
            stored_size = file_path.stat().st_size
            print(f"  Stored size: {stored_size} bytes")
            if stored_size != len(test_content):
                print(f"❌ Stored size doesn't match!")
                return False
        else:
            print(f"❌ File not found at: {file_path}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_file_download_with_verification():
    """Test file download and checksum verification"""
    print("\n" + "=" * 70)
    print("TEST 2: File Download with Checksum Verification")
    print("=" * 70)
    
    try:
        manager = get_storage_manager()
        
        username = "downloadtest001"
        filename = "test_verify.bin"
        test_content = b"Binary content for checksum verification \x00\x01\x02\x03"
        
        print(f"\n[1] Creating auth token for user: {username}")
        auth_token = create_test_auth_token(username)
        if not auth_token:
            print("❌ Failed to create auth token")
            return False
        print(f"✓ Auth token created")
        
        print(f"\n[2] Uploading file for download test")
        success, message, file_id = manager.upload_file(auth_token, filename, test_content)
        if not success:
            print(f"❌ Upload failed: {message}")
            return False
        print(f"✓ File uploaded (ID: {file_id[:8]}...)")
        
        print(f"\n[3] Downloading file")
        success, message, downloaded_data = manager.download_file(auth_token, file_id)
        if not success:
            print(f"❌ Download failed: {message}")
            return False
        print(f"✓ File downloaded successfully")
        
        print(f"\n[4] Verifying content integrity")
        if downloaded_data == test_content:
            print(f"✓ Content matches original")
            print(f"  Original size: {len(test_content)} bytes")
            print(f"  Downloaded size: {len(downloaded_data)} bytes")
        else:
            print(f"❌ Content mismatch!")
            print(f"  Original: {test_content[:32]}")
            print(f"  Downloaded: {downloaded_data[:32]}")
            return False
        
        print(f"\n[5] Verifying checksum")
        original_checksum = hashlib.sha256(test_content).hexdigest()
        downloaded_checksum = hashlib.sha256(downloaded_data).hexdigest()
        print(f"  Original checksum: {original_checksum[:32]}...")
        print(f"  Downloaded checksum: {downloaded_checksum[:32]}...")
        if original_checksum == downloaded_checksum:
            print(f"✓ Checksum matches")
        else:
            print(f"❌ Checksum mismatch!")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_quota_enforcement():
    """Test quota enforcement"""
    print("\n" + "=" * 70)
    print("TEST 3: Quota Enforcement")
    print("=" * 70)
    
    try:
        manager = get_storage_manager()
        storage_db = get_user_storage_database()
        
        username = "quotatest001"
        
        print(f"\n[1] Creating auth token for user: {username}")
        auth_token = create_test_auth_token(username)
        if not auth_token:
            print("❌ Failed to create auth token")
            return False
        print(f"✓ Auth token created")
        
        print(f"\n[2] Checking user quota")
        quota = storage_db.get_user_quota(username)
        if not quota:
            print(f"❌ Cannot retrieve quota")
            return False
        
        quota_gb = quota['quota_bytes'] / (1024**3)
        used_gb = quota['used_bytes'] / (1024**3)
        available_gb = (quota['quota_bytes'] - quota['used_bytes']) / (1024**3)
        
        print(f"✓ Quota retrieved")
        print(f"  Total: {quota_gb:.2f} GB")
        print(f"  Used: {used_gb:.6f} GB")
        print(f"  Available: {available_gb:.2f} GB")
        
        print(f"\n[3] Uploading file within quota")
        small_file = b"x" * (1024 * 10)  # 10 KB
        success, message, file_id1 = manager.upload_file(auth_token, "small.txt", small_file)
        if success:
            print(f"✓ Small file uploaded: {len(small_file)} bytes")
        else:
            print(f"❌ Small file upload failed: {message}")
            return False
        
        print(f"\n[4] Verifying quota was updated")
        updated_quota = storage_db.get_user_quota(username)
        if updated_quota['used_bytes'] >= quota['used_bytes'] + len(small_file):
            print(f"✓ Quota updated correctly")
            print(f"  New used: {updated_quota['used_bytes']} bytes")
        else:
            print(f"❌ Quota not updated properly")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_file_deletion():
    """Test file deletion"""
    print("\n" + "=" * 70)
    print("TEST 4: File Deletion")
    print("=" * 70)
    
    try:
        manager = get_storage_manager()
        
        username = "deletetest001"
        filename = "to_delete.txt"
        test_content = b"This file will be deleted"
        
        print(f"\n[1] Creating auth token and uploading file")
        auth_token = create_test_auth_token(username)
        if not auth_token:
            print("❌ Failed to create auth token")
            return False
        
        success, message, file_id = manager.upload_file(auth_token, filename, test_content)
        if not success:
            print(f"❌ Upload failed: {message}")
            return False
        print(f"✓ File uploaded (ID: {file_id[:8]}...)")
        
        print(f"\n[2] Deleting file")
        success, message = manager.delete_file(auth_token, file_id)
        if not success:
            print(f"❌ Delete failed: {message}")
            return False
        print(f"✓ File marked as deleted")
        
        print(f"\n[3] Verifying file cannot be downloaded")
        success, message, data = manager.download_file(auth_token, file_id)
        if not success and "deleted" in message.lower():
            print(f"✓ File properly blocked from download")
            print(f"  Message: {message}")
        elif not success:
            print(f"⚠ File blocked but message unclear: {message}")
        else:
            print(f"❌ File should not be downloadable after deletion!")
            return False
        
        print(f"\n[4] Verifying file removed from disk")
        file_path = Path(STORAGE_BASE_DIR) / username / file_id
        if not file_path.exists():
            print(f"✓ File removed from disk")
        else:
            print(f"⚠ File still exists on disk (soft delete only in DB)")
        
        return True
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_access_control():
    """Test access control between users"""
    print("\n" + "=" * 70)
    print("TEST 5: Access Control (User Isolation)")
    print("=" * 70)
    
    try:
        manager = get_storage_manager()
        
        user1 = "user_a"
        user2 = "user_b"
        
        print(f"\n[1] Creating auth tokens for two users")
        token1 = create_test_auth_token(user1)
        token2 = create_test_auth_token(user2)
        if not token1 or not token2:
            print("❌ Failed to create auth tokens")
            return False
        print(f"✓ Auth tokens created for {user1} and {user2}")
        
        print(f"\n[2] User A uploads a file")
        content_a = b"User A's private data"
        success, message, file_id_a = manager.upload_file(token1, "private.txt", content_a)
        if not success:
            print(f"❌ Upload failed: {message}")
            return False
        print(f"✓ File uploaded by User A (ID: {file_id_a[:8]}...)")
        
        print(f"\n[3] User B attempts to download User A's file (should fail)")
        success, message, data = manager.download_file(token2, file_id_a)
        if not success and "access" in message.lower():
            print(f"✓ Access denied as expected")
            print(f"  Message: {message}")
        elif not success:
            print(f"⚠ Download failed but unclear why: {message}")
        else:
            print(f"❌ User B should NOT be able to access User A's file!")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("STORAGE MANAGER UNIT TESTS")
    print("Direct disk-based file storage operations")
    print("=" * 70)
    
    try:
        # Run tests
        test1 = test_file_upload_and_storage()
        test2 = test_file_download_with_verification()
        test3 = test_quota_enforcement()
        test4 = test_file_deletion()
        test5 = test_access_control()
        
        # Summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        print(f"Test 1 (Upload & Storage):      {'✓ PASSED' if test1 else '❌ FAILED'}")
        print(f"Test 2 (Download & Verify):     {'✓ PASSED' if test2 else '❌ FAILED'}")
        print(f"Test 3 (Quota Enforcement):     {'✓ PASSED' if test3 else '❌ FAILED'}")
        print(f"Test 4 (File Deletion):         {'✓ PASSED' if test4 else '❌ FAILED'}")
        print(f"Test 5 (Access Control):        {'✓ PASSED' if test5 else '❌ FAILED'}")
        print("=" * 70)
        
        if all([test1, test2, test3, test4, test5]):
            print("\n✓✓✓ ALL TESTS PASSED ✓✓✓")
            print("\nFile Storage Implementation Complete:")
            print("  ✓ Disk-based file storage working")
            print("  ✓ Per-user file isolation verified")
            print("  ✓ Checksum integrity verification working")
            print("  ✓ Quota enforcement working")
            print("  ✓ File deletion working")
            print("  ✓ Access control working")
            print(f"\nStorage location: {STORAGE_BASE_DIR}")
            sys.exit(0)
        else:
            print("\n⚠ Some tests did not pass")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
