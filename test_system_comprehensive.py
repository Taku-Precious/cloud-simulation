"""
Comprehensive System Test Suite for Cloud Storage System
Tests all endpoints, authentication flows, file operations, and edge cases
"""

import requests
import json
import time
import tempfile
import hashlib
from pathlib import Path
from typing import Dict, Tuple, Optional

# Server configuration
API_BASE_URL = "http://127.0.0.1:8000"
HEADERS = {"Content-Type": "application/json"}

# Test data
TEST_USER_1 = {
    "username": "testuser1",
    "email": "testuser1@example.com",
    "password": "SecurePass123!@"
}

TEST_USER_2 = {
    "username": "testuser2",
    "email": "testuser2@example.com",
    "password": "AnotherPass456!@"
}


class TestResults:
    """Track test results"""
    def __init__(self):
        self.passed = []
        self.failed = []
        self.skipped = []
    
    def pass_test(self, test_name: str, message: str = ""):
        self.passed.append((test_name, message))
        print(f"✓ PASS: {test_name}" + (f" - {message}" if message else ""))
    
    def fail_test(self, test_name: str, message: str = "", error: str = ""):
        self.failed.append((test_name, message, error))
        print(f"✗ FAIL: {test_name}" + (f" - {message}" if message else ""))
        if error:
            print(f"  Error: {error}")
    
    def skip_test(self, test_name: str, reason: str = ""):
        self.skipped.append((test_name, reason))
        print(f"⊘ SKIP: {test_name}" + (f" - {reason}" if reason else ""))
    
    def summary(self):
        total = len(self.passed) + len(self.failed) + len(self.skipped)
        print(f"\n{'='*60}")
        print(f"TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Total Tests: {total}")
        print(f"Passed: {len(self.passed)} ✓")
        print(f"Failed: {len(self.failed)} ✗")
        print(f"Skipped: {len(self.skipped)} ⊘")
        print(f"{'='*60}")
        
        if self.failed:
            print(f"\nFailed Tests:")
            for test, msg, error in self.failed:
                print(f"  - {test}: {msg}")
                if error:
                    print(f"    {error}")
        
        success_rate = (len(self.passed) / total * 100) if total > 0 else 0
        print(f"\nSuccess Rate: {success_rate:.1f}%")
        return len(self.failed) == 0


results = TestResults()


# ============================================================================
# TEST 1: HEALTH CHECK
# ============================================================================

def test_health_check():
    """Test that the API is responding"""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            results.pass_test("Health Check", "API is responding")
            return True
        else:
            results.fail_test("Health Check", f"Got status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError as e:
        results.fail_test("Health Check", "Cannot connect to API", str(e))
        return False
    except Exception as e:
        results.fail_test("Health Check", "Unexpected error", str(e))
        return False


# ============================================================================
# TEST 2: ENDPOINT AVAILABILITY
# ============================================================================

def test_endpoints_available():
    """Test that all 11 endpoints are available"""
    endpoints = [
        ("GET", "/health"),
        ("GET", "/api/version"),
        ("POST", "/auth/register"),
        ("POST", "/auth/login"),
        ("POST", "/auth/verify-otp"),
        ("POST", "/storage/upload"),
        ("GET", "/storage/list"),
        ("GET", "/storage/quota"),
        ("GET", "/storage/account/info"),
    ]
    
    available = 0
    for method, endpoint in endpoints:
        try:
            if method == "GET":
                response = requests.get(f"{API_BASE_URL}{endpoint}", timeout=2)
            else:
                response = requests.post(f"{API_BASE_URL}{endpoint}", json={}, timeout=2)
            
            if response.status_code in [200, 400, 401, 403, 422]:
                available += 1
                results.pass_test(f"Endpoint {method} {endpoint}", "Available")
        except Exception as e:
            results.fail_test(f"Endpoint {method} {endpoint}", "Not available", str(e))
    
    return available >= 9  # At least 9/11 should be available


# ============================================================================
# TEST 3: REGISTRATION
# ============================================================================

def test_registration() -> Tuple[bool, Optional[str]]:
    """Test user registration"""
    payload = {
        "username": TEST_USER_1["username"],
        "email": TEST_USER_1["email"],
        "password": TEST_USER_1["password"]
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/register",
            json=payload,
            headers=HEADERS,
            timeout=5
        )
        
        if response.status_code == 201:
            data = response.json()
            if data.get("success"):
                results.pass_test("Registration", f"User {TEST_USER_1['username']} registered")
                return True, TEST_USER_1["username"]
            else:
                results.fail_test("Registration", f"API returned success=false: {data.get('message')}")
                return False, None
        elif response.status_code == 409:
            results.pass_test("Registration", "User already exists (409)")
            return True, TEST_USER_1["username"]
        else:
            results.fail_test("Registration", f"Got status {response.status_code}", response.text)
            return False, None
    except Exception as e:
        results.fail_test("Registration", "Request failed", str(e))
        return False, None


def test_registration_validation():
    """Test registration validation"""
    tests = [
        ({"username": "u", "email": "test@test.com", "password": "Pass123!"}, "Short username"),
        ({"username": "testuser", "email": "invalid", "password": "Pass123!"}, "Invalid email"),
        ({"username": "testuser", "email": "test@test.com", "password": "weak"}, "Weak password"),
    ]
    
    for payload, test_name in tests:
        try:
            response = requests.post(
                f"{API_BASE_URL}/auth/register",
                json=payload,
                headers=HEADERS,
                timeout=5
            )
            if response.status_code in [400, 422]:
                results.pass_test(f"Validation: {test_name}", "Rejected correctly")
            else:
                results.fail_test(f"Validation: {test_name}", f"Got status {response.status_code}")
        except Exception as e:
            results.fail_test(f"Validation: {test_name}", "Request failed", str(e))


# ============================================================================
# TEST 4: LOGIN & OTP
# ============================================================================

def test_login(username: str) -> Tuple[bool, Optional[str]]:
    """Test login request and OTP generation"""
    payload = {
        "username": username,
        "password": TEST_USER_1["password"]
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            json=payload,
            headers=HEADERS,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("session_id"):
                results.pass_test("Login", f"OTP sent to {data.get('email', 'user')}")
                return True, data.get("session_id")
            else:
                results.fail_test("Login", "No session_id in response")
                return False, None
        elif response.status_code == 401:
            results.fail_test("Login", "Invalid credentials", response.text)
            return False, None
        else:
            results.fail_test("Login", f"Got status {response.status_code}", response.text)
            return False, None
    except Exception as e:
        results.fail_test("Login", "Request failed", str(e))
        return False, None


def test_otp_verification(session_id: str) -> Tuple[bool, Optional[str]]:
    """Test OTP verification"""
    # Read OTP from database for testing
    try:
        import sqlite3
        db_path = Path("auth/auth.db")
        if not db_path.exists():
            results.skip_test("OTP Verification", "Database not accessible")
            return False, None
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT otp FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            results.fail_test("OTP Verification", "Session not found in database")
            return False, None
        
        otp = row["otp"]
        
        # Verify OTP
        payload = {
            "session_id": session_id,
            "otp": otp
        }
        
        response = requests.post(
            f"{API_BASE_URL}/auth/verify-otp",
            json=payload,
            headers=HEADERS,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("token"):
                results.pass_test("OTP Verification", "Token generated")
                return True, data.get("token")
            else:
                results.fail_test("OTP Verification", "No token in response")
                return False, None
        else:
            results.fail_test("OTP Verification", f"Got status {response.status_code}", response.text)
            return False, None
    
    except Exception as e:
        results.fail_test("OTP Verification", "Error reading database", str(e))
        return False, None


# ============================================================================
# TEST 5: FILE UPLOAD
# ============================================================================

def test_file_upload(token: str) -> Tuple[bool, Optional[str]]:
    """Test file upload"""
    try:
        # Create test file
        test_file_content = b"This is a test file for cloud storage system"
        
        files = {
            "file": ("test_file.txt", test_file_content, "text/plain")
        }
        
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.post(
            f"{API_BASE_URL}/storage/upload",
            files=files,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 201:
            data = response.json()
            if data.get("success") and data.get("file_id"):
                file_id = data.get("file_id")
                results.pass_test("File Upload", f"File {file_id} uploaded")
                return True, file_id
            else:
                results.fail_test("File Upload", "No file_id in response")
                return False, None
        elif response.status_code == 401:
            results.fail_test("File Upload", "Unauthorized", response.text)
            return False, None
        else:
            results.fail_test("File Upload", f"Got status {response.status_code}", response.text)
            return False, None
    
    except Exception as e:
        results.fail_test("File Upload", "Request failed", str(e))
        return False, None


# ============================================================================
# TEST 6: FILE LIST
# ============================================================================

def test_file_list(token: str) -> Tuple[bool, int]:
    """Test file listing"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(
            f"{API_BASE_URL}/storage/list",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                files = data.get("files", [])
                results.pass_test("File List", f"Listed {len(files)} file(s)")
                return True, len(files)
            else:
                results.fail_test("File List", "API returned success=false")
                return False, 0
        else:
            results.fail_test("File List", f"Got status {response.status_code}")
            return False, 0
    
    except Exception as e:
        results.fail_test("File List", "Request failed", str(e))
        return False, 0


# ============================================================================
# TEST 7: FILE DOWNLOAD
# ============================================================================

def test_file_download(token: str, file_id: str) -> bool:
    """Test file download"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(
            f"{API_BASE_URL}/storage/download/{file_id}",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            if response.content:
                results.pass_test("File Download", f"Downloaded {len(response.content)} bytes")
                return True
            else:
                results.fail_test("File Download", "Empty response")
                return False
        else:
            results.fail_test("File Download", f"Got status {response.status_code}")
            return False
    
    except Exception as e:
        results.fail_test("File Download", "Request failed", str(e))
        return False


# ============================================================================
# TEST 8: QUOTA CHECK
# ============================================================================

def test_quota(token: str) -> bool:
    """Test quota information"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(
            f"{API_BASE_URL}/storage/quota",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                used = data.get("used_bytes", 0)
                total = data.get("total_bytes", 0)
                results.pass_test("Quota Check", f"Used: {used} / {total} bytes")
                return True
            else:
                results.fail_test("Quota Check", "API returned success=false")
                return False
        else:
            results.fail_test("Quota Check", f"Got status {response.status_code}")
            return False
    
    except Exception as e:
        results.fail_test("Quota Check", "Request failed", str(e))
        return False


# ============================================================================
# TEST 9: FILE DELETE
# ============================================================================

def test_file_delete(token: str, file_id: str) -> bool:
    """Test file deletion"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.delete(
            f"{API_BASE_URL}/storage/{file_id}",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                results.pass_test("File Delete", "File deleted successfully")
                return True
            else:
                results.fail_test("File Delete", "API returned success=false")
                return False
        else:
            results.fail_test("File Delete", f"Got status {response.status_code}")
            return False
    
    except Exception as e:
        results.fail_test("File Delete", "Request failed", str(e))
        return False


# ============================================================================
# TEST 10: AUTHENTICATION ERRORS
# ============================================================================

def test_auth_errors():
    """Test authentication error handling"""
    tests = [
        ({"username": "invalid", "password": "pass"}, "Invalid login"),
        (("GET", "/storage/list", {}), "Missing token"),
    ]
    
    # Test invalid credentials
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            json={"username": "invaliduser123", "password": "invalidpass"},
            timeout=5
        )
        if response.status_code == 401:
            results.pass_test("Auth Error: Invalid credentials", "Rejected with 401")
        else:
            results.fail_test("Auth Error: Invalid credentials", f"Got {response.status_code}")
    except Exception as e:
        results.fail_test("Auth Error: Invalid credentials", str(e))
    
    # Test missing token
    try:
        response = requests.get(f"{API_BASE_URL}/storage/list", timeout=5)
        if response.status_code == 401:
            results.pass_test("Auth Error: Missing token", "Rejected with 401")
        else:
            results.fail_test("Auth Error: Missing token", f"Got {response.status_code}")
    except Exception as e:
        results.fail_test("Auth Error: Missing token", str(e))


# ============================================================================
# TEST 11: ACCOUNT INFO
# ============================================================================

def test_account_info(token: str) -> bool:
    """Test account information endpoint"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(
            f"{API_BASE_URL}/storage/account/info",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                results.pass_test("Account Info", f"User: {data.get('username')}")
                return True
            else:
                results.fail_test("Account Info", "API returned success=false")
                return False
        else:
            results.fail_test("Account Info", f"Got status {response.status_code}")
            return False
    
    except Exception as e:
        results.fail_test("Account Info", "Request failed", str(e))
        return False


# ============================================================================
# MAIN TEST EXECUTION
# ============================================================================

def main():
    print("="*60)
    print("CLOUD STORAGE SYSTEM - COMPREHENSIVE TEST SUITE")
    print("="*60)
    print(f"API Base URL: {API_BASE_URL}")
    print(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    print()
    
    # Test 1: Health Check
    if not test_health_check():
        print("\n⚠ API is not responding. Aborting tests.")
        return
    
    time.sleep(1)
    
    # Test 2: Endpoints available
    print("\n[Testing Endpoint Availability]")
    test_endpoints_available()
    
    # Test 3: Registration
    print("\n[Testing Authentication]")
    test_registration_validation()
    success, username = test_registration()
    if not success or not username:
        print("\n⚠ Registration failed. Skipping dependent tests.")
        results.summary()
        return
    
    time.sleep(1)
    
    # Test 4: Login
    success, session_id = test_login(username)
    if not success or not session_id:
        print("\n⚠ Login failed. Skipping dependent tests.")
        results.summary()
        return
    
    time.sleep(1)
    
    # Test 5: OTP Verification
    success, token = test_otp_verification(session_id)
    if not success or not token:
        print("\n⚠ OTP verification failed. Skipping dependent tests.")
        results.summary()
        return
    
    time.sleep(1)
    
    # Test 6: Authentication Errors
    print("\n[Testing Auth Error Handling]")
    test_auth_errors()
    
    # Test 7: Account Info
    print("\n[Testing Account Operations]")
    test_account_info(token)
    
    # Test 8: File Operations
    print("\n[Testing File Operations]")
    test_quota(token)
    
    success, file_id = test_file_upload(token)
    if success and file_id:
        time.sleep(1)
        test_file_list(token)
        time.sleep(0.5)
        test_file_download(token, file_id)
        time.sleep(0.5)
        test_file_delete(token, file_id)
    
    # Summary
    print()
    results.summary()
    
    if results.summary():
        print("\n✓ All critical tests PASSED! System is ready for frontend development.")
    else:
        print("\n✗ Some tests FAILED. Review errors above.")


if __name__ == "__main__":
    main()
