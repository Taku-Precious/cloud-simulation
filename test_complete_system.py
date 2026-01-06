"""
Comprehensive System Test Suite
Tests all components: gRPC backend, FastAPI wrapper, auth, storage, quotas
"""
import requests
import json
import time
from pathlib import Path
import hashlib

BASE_URL = "http://127.0.0.1:8000"

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add_pass(self, test_name, message=""):
        self.passed += 1
        self.tests.append(("✅ PASS", test_name, message))
        print(f"✅ PASS: {test_name} {message}")
    
    def add_fail(self, test_name, message=""):
        self.failed += 1
        self.tests.append(("❌ FAIL", test_name, message))
        print(f"❌ FAIL: {test_name} {message}")
    
    def summary(self):
        print("\n" + "="*70)
        print(f"TEST RESULTS: {self.passed} passed, {self.failed} failed")
        print("="*70)
        for status, name, msg in self.tests:
            print(f"{status} {name}" + (f" - {msg}" if msg else ""))
        print("="*70)

results = TestResults()

# ============================================================================
# SECTION 1: HEALTH CHECK
# ============================================================================
print("\n[SECTION 1] HEALTH CHECK")
print("="*70)

try:
    response = requests.get(f"{BASE_URL}/health", timeout=5)
    if response.status_code == 200:
        results.add_pass("Health Check", f"Status: {response.status_code}")
    else:
        results.add_fail("Health Check", f"Expected 200, got {response.status_code}")
except Exception as e:
    results.add_fail("Health Check", str(e))

# ============================================================================
# SECTION 2: REGISTRATION & AUTHENTICATION
# ============================================================================
print("\n[SECTION 2] REGISTRATION & AUTHENTICATION")
print("="*70)

test_user = "testuser_" + str(int(time.time()))
test_email = f"{test_user}@test.com"
test_password = "SecurePass123!"

# Test 2.1: Register User
print(f"\nTest 2.1: Registering user '{test_user}'...")
try:
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={
            "username": test_user,
            "email": test_email,
            "password": test_password
        },
        timeout=5
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 201:
        data = response.json()
        results.add_pass("Register User", f"User '{test_user}' created")
    else:
        results.add_fail("Register User", f"Status {response.status_code}: {response.text}")
except Exception as e:
    results.add_fail("Register User", str(e))

# Test 2.2: Login Request (OTP)
print(f"\nTest 2.2: Login request for '{test_user}'...")
try:
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "username": test_user,
            "password": test_password
        },
        timeout=5
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}...")
    
    if response.status_code == 200:
        data = response.json()
        session_id = data.get("session_id")
        if session_id:
            results.add_pass("Login Request", f"OTP sent, session_id: {session_id[:20]}...")
            
            # Get OTP from database for testing
            from auth.database import get_database
            db = get_database()
            session = db.get_session(session_id)
            if session:
                otp_code = session['otp']
                results.add_pass("OTP Retrieval", f"OTP code: {otp_code}")
            else:
                results.add_fail("OTP Retrieval", "Session not found in database")
        else:
            results.add_fail("Login Request", "No session_id in response")
    else:
        results.add_fail("Login Request", f"Status {response.status_code}")
except Exception as e:
    results.add_fail("Login Request", str(e))

# Test 2.3: OTP Verification
print(f"\nTest 2.3: OTP verification...")
try:
    if 'session_id' in locals() and 'otp_code' in locals():
        response = requests.post(
            f"{BASE_URL}/auth/verify-otp",
            json={
                "session_id": session_id,
                "otp": otp_code
            },
            timeout=5
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:200]}...")
        
        if response.status_code == 200:
            data = response.json()
            auth_token = data.get("token")
            if auth_token:
                results.add_pass("OTP Verification", f"Auth token generated")
            else:
                results.add_fail("OTP Verification", "No token in response")
        else:
            results.add_fail("OTP Verification", f"Status {response.status_code}: {response.text}")
    else:
        results.add_fail("OTP Verification", "Session or OTP not available")
except Exception as e:
    results.add_fail("OTP Verification", str(e))

# ============================================================================
# SECTION 3: FILE STORAGE OPERATIONS
# ============================================================================
print("\n[SECTION 3] FILE STORAGE OPERATIONS")
print("="*70)

if 'auth_token' not in locals():
    results.add_fail("File Operations", "Auth token not available, skipping file tests")
else:
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    # Test 3.1: Upload File
    print("\nTest 3.1: Uploading test file...")
    test_file_content = b"This is a test file for cloud storage system."
    test_file_hash = hashlib.sha256(test_file_content).hexdigest()
    
    try:
        files = {"file": ("test_document.txt", test_file_content)}
        response = requests.post(
            f"{BASE_URL}/storage/upload",
            files=files,
            headers=headers,
            timeout=10
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:200]}...")
        
        if response.status_code == 200:
            data = response.json()
            file_id = data.get("file_id")
            if file_id:
                results.add_pass("Upload File", f"File uploaded, ID: {file_id}")
            else:
                results.add_fail("Upload File", "No file_id in response")
        else:
            results.add_fail("Upload File", f"Status {response.status_code}: {response.text}")
    except Exception as e:
        results.add_fail("Upload File", str(e))
    
    # Test 3.2: List Files
    print("\nTest 3.2: Listing files...")
    try:
        response = requests.get(
            f"{BASE_URL}/storage/list",
            headers=headers,
            timeout=5
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:200]}...")
        
        if response.status_code == 200:
            data = response.json()
            files = data.get("files", [])
            results.add_pass("List Files", f"Found {len(files)} file(s)")
        else:
            results.add_fail("List Files", f"Status {response.status_code}")
    except Exception as e:
        results.add_fail("List Files", str(e))
    
    # Test 3.3: Download File
    print("\nTest 3.3: Downloading file...")
    if 'file_id' in locals():
        try:
            response = requests.get(
                f"{BASE_URL}/storage/download/{file_id}",
                headers=headers,
                timeout=10
            )
            print(f"Status: {response.status_code}")
            print(f"Content length: {len(response.content)}")
            
            if response.status_code == 200:
                # Verify content
                if response.content == test_file_content:
                    results.add_pass("Download File", "Content verified, matches uploaded file")
                else:
                    results.add_fail("Download File", "Downloaded content doesn't match uploaded file")
            else:
                results.add_fail("Download File", f"Status {response.status_code}")
        except Exception as e:
            results.add_fail("Download File", str(e))
    else:
        results.add_fail("Download File", "File ID not available")
    
    # Test 3.4: Get Quota
    print("\nTest 3.4: Checking quota...")
    try:
        response = requests.get(
            f"{BASE_URL}/storage/quota",
            headers=headers,
            timeout=5
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            used = data.get("used_bytes", 0)
            total = data.get("total_bytes", 0)
            results.add_pass("Get Quota", f"Used: {used}B / {total}B")
        else:
            results.add_fail("Get Quota", f"Status {response.status_code}")
    except Exception as e:
        results.add_fail("Get Quota", str(e))
    
    # Test 3.5: Delete File
    print("\nTest 3.5: Deleting file...")
    if 'file_id' in locals():
        try:
            response = requests.delete(
                f"{BASE_URL}/storage/{file_id}",
                headers=headers,
                timeout=5
            )
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            
            if response.status_code == 200:
                results.add_pass("Delete File", "File deleted successfully")
                
                # Verify deletion
                response = requests.get(
                    f"{BASE_URL}/storage/download/{file_id}",
                    headers=headers,
                    timeout=5
                )
                if response.status_code == 404:
                    results.add_pass("Verify Deletion", "File confirmed deleted (404)")
                else:
                    results.add_fail("Verify Deletion", f"File still exists (status {response.status_code})")
            else:
                results.add_fail("Delete File", f"Status {response.status_code}")
        except Exception as e:
            results.add_fail("Delete File", str(e))
    else:
        results.add_fail("Delete File", "File ID not available")

# ============================================================================
# SECTION 4: ERROR HANDLING & EDGE CASES
# ============================================================================
print("\n[SECTION 4] ERROR HANDLING & EDGE CASES")
print("="*70)

# Test 4.1: Invalid credentials
print("\nTest 4.1: Invalid login credentials...")
try:
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "username": "nonexistent_user",
            "password": "wrongpassword"
        },
        timeout=5
    )
    print(f"Status: {response.status_code}")
    
    if response.status_code == 401:
        results.add_pass("Invalid Credentials", "Correctly rejected")
    else:
        results.add_fail("Invalid Credentials", f"Expected 401, got {response.status_code}")
except Exception as e:
    results.add_fail("Invalid Credentials", str(e))

# Test 4.2: Missing auth header
print("\nTest 4.2: Missing authorization header...")
try:
    response = requests.get(
        f"{BASE_URL}/storage/list",
        timeout=5
    )
    print(f"Status: {response.status_code}")
    
    if response.status_code == 401:
        results.add_pass("Missing Auth Header", "Correctly rejected")
    else:
        results.add_fail("Missing Auth Header", f"Expected 401, got {response.status_code}")
except Exception as e:
    results.add_fail("Missing Auth Header", str(e))

# Test 4.3: Invalid auth token
print("\nTest 4.3: Invalid authorization token...")
try:
    response = requests.get(
        f"{BASE_URL}/storage/list",
        headers={"Authorization": "Bearer invalid_token_12345"},
        timeout=5
    )
    print(f"Status: {response.status_code}")
    
    if response.status_code == 401:
        results.add_pass("Invalid Auth Token", "Correctly rejected")
    else:
        results.add_fail("Invalid Auth Token", f"Expected 401, got {response.status_code}")
except Exception as e:
    results.add_fail("Invalid Auth Token", str(e))

# Test 4.4: Download non-existent file
print("\nTest 4.4: Download non-existent file...")
if 'auth_token' in locals():
    try:
        response = requests.get(
            f"{BASE_URL}/storage/download/nonexistent_file_id",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=5
        )
        print(f"Status: {response.status_code}")
        
        if response.status_code == 404:
            results.add_pass("Non-existent File", "Correctly rejected with 404")
        else:
            results.add_fail("Non-existent File", f"Expected 404, got {response.status_code}")
    except Exception as e:
        results.add_fail("Non-existent File", str(e))
else:
    results.add_fail("Non-existent File", "Auth token not available")

# Test 4.5: Duplicate registration
print("\nTest 4.5: Duplicate email registration...")
try:
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={
            "username": "another_user_" + str(int(time.time())),
            "email": test_email,  # Use same email as first user
            "password": "AnotherPass123!"
        },
        timeout=5
    )
    print(f"Status: {response.status_code}")
    
    if response.status_code == 400 or response.status_code == 409:
        results.add_pass("Duplicate Email", f"Correctly rejected (status {response.status_code})")
    else:
        results.add_fail("Duplicate Email", f"Expected 400/409, got {response.status_code}")
except Exception as e:
    results.add_fail("Duplicate Email", str(e))

# ============================================================================
# FINAL SUMMARY
# ============================================================================
results.summary()

# Exit with appropriate code
exit(0 if results.failed == 0 else 1)
