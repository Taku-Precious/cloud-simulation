"""
Comprehensive REST API Integration Test Suite
Tests all FastAPI endpoints with real authentication and file operations
"""

import requests
import json
import time
import sys
from pathlib import Path

# Configuration
API_BASE_URL = "http://localhost:8001"
TIMEOUT = 30

# Test data
TEST_USER_1 = {
    "username": "testuser01",
    "email": "testuser01@example.com",
    "password": "TestPassword123!"
}

TEST_USER_2 = {
    "username": "testuser02",
    "email": "testuser02@example.com",
    "password": "TestPassword456!"
}

# Global state
auth_token_1 = None
auth_token_2 = None
session_id_1 = None
uploaded_file_id = None


def print_section(title):
    """Print test section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_test(name, passed, message=""):
    """Print test result"""
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  [{status}] {name}")
    if message:
        print(f"         {message}")


def print_response(response, title="Response"):
    """Pretty print HTTP response"""
    print(f"\n  {title}:")
    print(f"    Status: {response.status_code}")
    try:
        data = response.json()
        print(f"    Body: {json.dumps(data, indent=6)}")
    except:
        print(f"    Body: {response.text[:200]}")


# ============================================================================
# HEALTH & INFO TESTS
# ============================================================================

def test_health_check():
    """Test health check endpoint"""
    print_section("Test 1: Health Check")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/health",
            timeout=TIMEOUT
        )
        
        print_response(response)
        
        passed = response.status_code == 200
        data = response.json()
        passed = passed and data.get("success") == True
        
        print_test("Health check", passed)
        return passed
    
    except Exception as e:
        print_test("Health check", False, str(e))
        return False


def test_api_version():
    """Test API version endpoint"""
    print_section("Test 2: API Version")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/version",
            timeout=TIMEOUT
        )
        
        print_response(response)
        
        passed = response.status_code == 200
        data = response.json()
        passed = passed and "version" in data
        
        print_test("Version endpoint", passed, f"API Version: {data.get('version')}")
        return passed
    
    except Exception as e:
        print_test("Version endpoint", False, str(e))
        return False


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

def test_user_registration():
    """Test user registration endpoint"""
    global auth_token_1, auth_token_2
    
    print_section("Test 3: User Registration")
    
    # Test User 1 Registration
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/register",
            json=TEST_USER_1,
            timeout=TIMEOUT
        )
        
        print(f"\n  User 1 Registration:")
        print_response(response, "Register User 1")
        
        passed = response.status_code == 201
        data = response.json()
        passed = passed and data.get("success") == True
        
        print_test("User 1 registration", passed)
        
        if not passed:
            return False
    
    except Exception as e:
        print_test("User 1 registration", False, str(e))
        return False
    
    # Test User 2 Registration
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/register",
            json=TEST_USER_2,
            timeout=TIMEOUT
        )
        
        print(f"\n  User 2 Registration:")
        print_response(response, "Register User 2")
        
        passed = response.status_code == 201
        data = response.json()
        passed = passed and data.get("success") == True
        
        print_test("User 2 registration", passed)
        return passed
    
    except Exception as e:
        print_test("User 2 registration", False, str(e))
        return False


def test_user_login():
    """Test user login endpoint"""
    global session_id_1
    
    print_section("Test 4: User Login (OTP Request)")
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            json={
                "username": TEST_USER_1["username"],
                "password": TEST_USER_1["password"]
            },
            timeout=TIMEOUT
        )
        
        print_response(response)
        
        passed = response.status_code == 200
        data = response.json()
        passed = passed and data.get("success") == True
        session_id_1 = data.get("session_id")
        passed = passed and session_id_1 is not None
        
        print_test("Login with OTP request", passed, f"Session ID: {session_id_1[:20]}..." if session_id_1 else "")
        return passed
    
    except Exception as e:
        print_test("Login with OTP request", False, str(e))
        return False


def test_otp_verification():
    """Test OTP verification endpoint"""
    global auth_token_1
    
    print_section("Test 5: OTP Verification")
    
    if not session_id_1:
        print_test("OTP verification", False, "No session ID from login")
        return False
    
    try:
        # Get OTP from database (for testing purposes)
        from auth.database import get_database
        db = get_database()
        session = db.get_session(session_id_1)
        
        if not session:
            print_test("OTP verification", False, "Session not found in database")
            return False
        
        otp = session['otp']
        print(f"\n  Using OTP from database: {otp}")
        
        response = requests.post(
            f"{API_BASE_URL}/auth/verify-otp",
            json={
                "session_id": session_id_1,
                "username": TEST_USER_1["username"],
                "otp": otp
            },
            timeout=TIMEOUT
        )
        
        print_response(response)
        
        passed = response.status_code == 200
        data = response.json()
        passed = passed and data.get("success") == True
        auth_token_1 = data.get("auth_token")
        passed = passed and auth_token_1 is not None
        
        print_test("OTP verification", passed, f"Auth Token: {auth_token_1[:20]}..." if auth_token_1 else "")
        return passed
    
    except Exception as e:
        print_test("OTP verification", False, str(e))
        return False


def test_login_user_2():
    """Test login for User 2 and get auth token"""
    global auth_token_2, session_id_1
    
    print_section("Test 6: User 2 Login & OTP")
    
    try:
        # Login
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            json={
                "username": TEST_USER_2["username"],
                "password": TEST_USER_2["password"]
            },
            timeout=TIMEOUT
        )
        
        passed = response.status_code == 200
        data = response.json()
        session_id_2 = data.get("session_id")
        
        if not passed or not session_id_2:
            print_test("User 2 login", False)
            return False
        
        print_test("User 2 login", True, f"Session ID obtained")
        
        # OTP Verification
        from auth.database import get_database
        db = get_database()
        session = db.get_session(session_id_2)
        otp = session['otp']
        
        response = requests.post(
            f"{API_BASE_URL}/auth/verify-otp",
            json={
                "session_id": session_id_2,
                "username": TEST_USER_2["username"],
                "otp": otp
            },
            timeout=TIMEOUT
        )
        
        passed = response.status_code == 200
        data = response.json()
        auth_token_2 = data.get("auth_token")
        passed = passed and auth_token_2 is not None
        
        print_test("User 2 OTP verification", passed, f"Auth Token obtained")
        return passed
    
    except Exception as e:
        print_test("User 2 login & OTP", False, str(e))
        return False


# ============================================================================
# FILE OPERATIONS TESTS
# ============================================================================

def test_file_upload():
    """Test file upload endpoint"""
    global uploaded_file_id, auth_token_1
    
    print_section("Test 7: File Upload")
    
    if not auth_token_1:
        print_test("File upload", False, "Not authenticated")
        return False
    
    try:
        # Create test file content
        test_content = b"This is a test file for cloud storage. It contains important data."
        
        # Prepare multipart form data
        files = {
            'file': ('test_document.txt', test_content, 'text/plain')
        }
        
        response = requests.post(
            f"{API_BASE_URL}/storage/upload",
            files=files,
            headers={"Authorization": f"Bearer {auth_token_1}"},
            timeout=TIMEOUT
        )
        
        print_response(response)
        
        passed = response.status_code == 201
        data = response.json()
        passed = passed and data.get("success") == True
        uploaded_file_id = data.get("file_id")
        passed = passed and uploaded_file_id is not None
        
        file_size = data.get("file_size", 0)
        print_test("File upload", passed, f"File ID: {uploaded_file_id[:20]}... Size: {file_size} bytes")
        return passed
    
    except Exception as e:
        print_test("File upload", False, str(e))
        return False


def test_file_list():
    """Test file list endpoint"""
    global auth_token_1
    
    print_section("Test 8: File List")
    
    if not auth_token_1:
        print_test("File list", False, "Not authenticated")
        return False
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/storage/list",
            headers={"Authorization": f"Bearer {auth_token_1}"},
            timeout=TIMEOUT
        )
        
        print_response(response)
        
        passed = response.status_code == 200
        data = response.json()
        passed = passed and data.get("success") == True
        files = data.get("files", [])
        total_count = data.get("total_count", 0)
        
        print_test("File list", passed, f"Found {total_count} files")
        return passed
    
    except Exception as e:
        print_test("File list", False, str(e))
        return False


def test_file_download():
    """Test file download endpoint"""
    global uploaded_file_id, auth_token_1
    
    print_section("Test 9: File Download")
    
    if not auth_token_1 or not uploaded_file_id:
        print_test("File download", False, "File not uploaded or not authenticated")
        return False
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/storage/download/{uploaded_file_id}",
            headers={"Authorization": f"Bearer {auth_token_1}"},
            timeout=TIMEOUT
        )
        
        passed = response.status_code == 200
        content_length = len(response.content)
        
        print(f"\n  Download Response:")
        print(f"    Status: {response.status_code}")
        print(f"    Content-Type: {response.headers.get('content-type')}")
        print(f"    Content-Length: {content_length} bytes")
        
        print_test("File download", passed, f"Downloaded {content_length} bytes")
        return passed
    
    except Exception as e:
        print_test("File download", False, str(e))
        return False


def test_quota_info():
    """Test quota information endpoint"""
    global auth_token_1
    
    print_section("Test 10: Quota Information")
    
    if not auth_token_1:
        print_test("Quota info", False, "Not authenticated")
        return False
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/storage/quota",
            headers={"Authorization": f"Bearer {auth_token_1}"},
            timeout=TIMEOUT
        )
        
        print_response(response)
        
        passed = response.status_code == 200
        data = response.json()
        passed = passed and data.get("success") == True
        
        quota_gb = data.get("total_quota_gb", 0)
        used_gb = data.get("used_gb", 0)
        available_gb = data.get("available_gb", 0)
        usage_pct = data.get("usage_percentage", 0)
        
        info = f"Total: {quota_gb:.2f}GB, Used: {used_gb:.2f}GB, Available: {available_gb:.2f}GB, Usage: {usage_pct:.1f}%"
        print_test("Quota info", passed, info)
        return passed
    
    except Exception as e:
        print_test("Quota info", False, str(e))
        return False


def test_access_control():
    """Test access control - User 2 cannot download User 1's file"""
    global uploaded_file_id, auth_token_2
    
    print_section("Test 11: Access Control (Cross-User)")
    
    if not auth_token_2 or not uploaded_file_id:
        print_test("Access control", False, "Prerequisite failed")
        return False
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/storage/download/{uploaded_file_id}",
            headers={"Authorization": f"Bearer {auth_token_2}"},
            timeout=TIMEOUT
        )
        
        # Should be forbidden
        passed = response.status_code in [403, 404]
        
        print(f"\n  Access Control Test:")
        print(f"    Status: {response.status_code}")
        print(f"    Body: {response.json()}")
        
        print_test("Access control", passed, "User 2 correctly denied access")
        return passed
    
    except Exception as e:
        print_test("Access control", False, str(e))
        return False


def test_file_delete():
    """Test file deletion endpoint"""
    global uploaded_file_id, auth_token_1
    
    print_section("Test 12: File Deletion")
    
    if not auth_token_1 or not uploaded_file_id:
        print_test("File delete", False, "File not uploaded or not authenticated")
        return False
    
    try:
        response = requests.delete(
            f"{API_BASE_URL}/storage/{uploaded_file_id}",
            headers={"Authorization": f"Bearer {auth_token_1}"},
            timeout=TIMEOUT
        )
        
        print_response(response)
        
        passed = response.status_code == 200
        data = response.json()
        passed = passed and data.get("success") == True
        
        print_test("File delete", passed, f"File {uploaded_file_id[:20]}... deleted")
        return passed
    
    except Exception as e:
        print_test("File delete", False, str(e))
        return False


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

def test_auth_errors():
    """Test authentication error handling"""
    print_section("Test 13: Authentication Error Handling")
    
    # Invalid credentials
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            json={"username": "invalid_user", "password": "wrong_password"},
            timeout=TIMEOUT
        )
        
        passed = response.status_code == 401
        print_test("Invalid credentials", passed, f"Status: {response.status_code}")
        
        if not passed:
            return False
    
    except Exception as e:
        print_test("Invalid credentials", False, str(e))
        return False
    
    # Missing auth header
    try:
        response = requests.get(
            f"{API_BASE_URL}/storage/list",
            timeout=TIMEOUT
        )
        
        passed = response.status_code == 401
        print_test("Missing auth header", passed, f"Status: {response.status_code}")
        return passed
    
    except Exception as e:
        print_test("Missing auth header", False, str(e))
        return False


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests():
    """Run all API tests in sequence"""
    print("\n" + "="*70)
    print("  CLOUD STORAGE API - COMPREHENSIVE TEST SUITE")
    print("  Testing all REST endpoints with full authentication flow")
    print("="*70)
    
    results = []
    
    # Info Tests
    results.append(("Health Check", test_health_check()))
    results.append(("API Version", test_api_version()))
    
    # Authentication Tests
    results.append(("User Registration", test_user_registration()))
    results.append(("User Login", test_user_login()))
    results.append(("OTP Verification", test_otp_verification()))
    results.append(("User 2 Login", test_login_user_2()))
    
    # File Operations Tests
    results.append(("File Upload", test_file_upload()))
    results.append(("File List", test_file_list()))
    results.append(("File Download", test_file_download()))
    results.append(("Quota Info", test_quota_info()))
    results.append(("Access Control", test_access_control()))
    results.append(("File Delete", test_file_delete()))
    
    # Error Handling Tests
    results.append(("Auth Error Handling", test_auth_errors()))
    
    # Print Summary
    print_section("TEST SUMMARY")
    passed_count = sum(1 for _, result in results if result)
    total_count = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  [{status}] {test_name}")
    
    print(f"\n  Total: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print(f"\n  🎉 ALL TESTS PASSED! 🎉")
        print(f"\n  REST API fully functional:")
        print(f"    - Authentication: working (register, login, OTP)")
        print(f"    - File Storage: working (upload, download, list, delete)")
        print(f"    - Quota Management: working")
        print(f"    - Access Control: working")
        print(f"    - Error Handling: working")
        return 0
    else:
        print(f"\n  ⚠️  Some tests failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = run_all_tests()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n✗ Test suite error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
