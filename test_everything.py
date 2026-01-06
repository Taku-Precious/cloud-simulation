"""
Comprehensive test suite for cloud storage system.
Tests gRPC backend, REST API, file storage, quotas, and security.
"""

import requests
import json
import time
import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class TestSuite:
    """Comprehensive test suite for cloud storage system."""
    
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.test_users = []
        self.auth_tokens = {}
        self.session_ids = {}
        self.test_results = []
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
    
    def print_header(self, text):
        """Print a formatted header."""
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}")
        print(f"{text:^70}")
        print(f"{'='*70}{Colors.ENDC}\n")
    
    def print_subheader(self, text):
        """Print a formatted subheader."""
        print(f"{Colors.OKBLUE}{Colors.BOLD}► {text}{Colors.ENDC}")
    
    def print_success(self, msg):
        """Print success message."""
        print(f"{Colors.OKGREEN}✓ {msg}{Colors.ENDC}")
    
    def print_fail(self, msg):
        """Print failure message."""
        print(f"{Colors.FAIL}✗ {msg}{Colors.ENDC}")
    
    def print_warning(self, msg):
        """Print warning message."""
        print(f"{Colors.WARNING}⚠ {msg}{Colors.ENDC}")
    
    def log_result(self, test_name, passed, message=""):
        """Log test result."""
        self.total_tests += 1
        if passed:
            self.passed_tests += 1
            self.print_success(f"{test_name}")
        else:
            self.failed_tests += 1
            self.print_fail(f"{test_name}")
            if message:
                print(f"  Details: {message}")
        self.test_results.append({
            'test': test_name,
            'passed': passed,
            'message': message
        })
    
    def test_health_check(self):
        """Test health check endpoint."""
        self.print_subheader("Health Check")
        try:
            response = requests.get(f"{self.base_url}/health")
            if response.status_code == 200:
                self.log_result("Health check", True)
                return True
            else:
                self.log_result("Health check", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Health check", False, str(e))
            return False
    
    def test_registration(self):
        """Test user registration."""
        self.print_subheader("User Registration")
        
        test_users = [
            {"username": f"testuser_{int(time.time())}", "email": f"test{int(time.time())}@example.com", "password": "TestPass123!"},
            {"username": f"testuser2_{int(time.time())}", "email": f"test2{int(time.time())}@example.com", "password": "TestPass456!"},
        ]
        
        for user in test_users:
            try:
                response = requests.post(
                    f"{self.base_url}/auth/register",
                    json=user
                )
                
                if response.status_code == 201:
                    self.test_users.append(user)
                    self.log_result(f"Register {user['username']}", True)
                else:
                    self.log_result(f"Register {user['username']}", False, f"Status: {response.status_code}, Response: {response.text}")
            except Exception as e:
                self.log_result(f"Register {user['username']}", False, str(e))
    
    def test_login_and_otp(self):
        """Test login and OTP verification."""
        self.print_subheader("Login & OTP Verification")
        
        if not self.test_users:
            self.print_warning("No test users available. Skipping login tests.")
            return
        
        for user in self.test_users:
            try:
                # Step 1: Login request
                login_response = requests.post(
                    f"{self.base_url}/auth/login",
                    json={"username": user['username'], "password": user['password']}
                )
                
                if login_response.status_code != 200:
                    self.log_result(f"Login {user['username']}", False, f"Status: {login_response.status_code}")
                    continue
                
                login_data = login_response.json()
                if login_data['status'] != 'success':
                    self.log_result(f"Login {user['username']}", False, login_data.get('message', 'Unknown error'))
                    continue
                
                self.log_result(f"Login {user['username']}", True)
                
                # Step 2: OTP Verification
                session_id = login_data['data']['session_id']
                # In test, use the OTP from the response or a hardcoded test OTP
                otp_code = "123456"  # Default test OTP
                
                otp_response = requests.post(
                    f"{self.base_url}/auth/verify-otp",
                    json={"session_id": session_id, "otp": otp_code}
                )
                
                if otp_response.status_code == 200:
                    otp_data = otp_response.json()
                    if otp_data['status'] == 'success':
                        auth_token = otp_data['data']['auth_token']
                        self.auth_tokens[user['username']] = auth_token
                        self.session_ids[user['username']] = session_id
                        self.log_result(f"OTP verification {user['username']}", True)
                    else:
                        self.log_result(f"OTP verification {user['username']}", False, otp_data.get('message'))
                else:
                    self.log_result(f"OTP verification {user['username']}", False, f"Status: {otp_response.status_code}")
            
            except Exception as e:
                self.log_result(f"Login/OTP {user['username']}", False, str(e))
    
    def test_account_info(self):
        """Test account info endpoint."""
        self.print_subheader("Account Information")
        
        if not self.auth_tokens:
            self.print_warning("No authenticated users. Skipping account info tests.")
            return
        
        for username, token in self.auth_tokens.items():
            try:
                response = requests.get(
                    f"{self.base_url}/storage/account/info",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data['status'] == 'success':
                        self.log_result(f"Account info {username}", True)
                    else:
                        self.log_result(f"Account info {username}", False, data.get('message'))
                else:
                    self.log_result(f"Account info {username}", False, f"Status: {response.status_code}")
            except Exception as e:
                self.log_result(f"Account info {username}", False, str(e))
    
    def test_quota_info(self):
        """Test quota information endpoint."""
        self.print_subheader("Quota Information")
        
        if not self.auth_tokens:
            self.print_warning("No authenticated users. Skipping quota tests.")
            return
        
        for username, token in self.auth_tokens.items():
            try:
                response = requests.get(
                    f"{self.base_url}/storage/quota",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data['status'] == 'success':
                        quota_data = data['data']
                        total_gb = quota_data['total_gb']
                        used_gb = quota_data['used_gb']
                        available_gb = quota_data['available_gb']
                        self.log_result(
                            f"Quota {username}", True,
                            f"Total: {total_gb}GB, Used: {used_gb:.2f}GB, Available: {available_gb:.2f}GB"
                        )
                    else:
                        self.log_result(f"Quota {username}", False, data.get('message'))
                else:
                    self.log_result(f"Quota {username}", False, f"Status: {response.status_code}")
            except Exception as e:
                self.log_result(f"Quota {username}", False, str(e))
    
    def test_file_upload(self):
        """Test file upload functionality."""
        self.print_subheader("File Upload")
        
        if not self.auth_tokens:
            self.print_warning("No authenticated users. Skipping file upload tests.")
            return
        
        # Create test files
        test_files = [
            ("test_file_1.txt", "This is test file 1 content"),
            ("test_file_2.json", json.dumps({"test": "data", "value": 123})),
            ("test_file_3.txt", "A" * 1000),  # 1KB file
        ]
        
        for username, token in self.auth_tokens.items():
            self.file_ids = {}
            
            for filename, content in test_files:
                try:
                    files = {
                        'file': (filename, content.encode() if isinstance(content, str) else content)
                    }
                    
                    response = requests.post(
                        f"{self.base_url}/storage/upload",
                        files=files,
                        headers={"Authorization": f"Bearer {token}"}
                    )
                    
                    if response.status_code == 201:
                        data = response.json()
                        if data['status'] == 'success':
                            file_id = data['data']['file_id']
                            if not hasattr(self, 'file_ids'):
                                self.file_ids = {}
                            self.file_ids[filename] = file_id
                            self.log_result(f"Upload {filename} ({username})", True, f"File ID: {file_id}")
                        else:
                            self.log_result(f"Upload {filename}", False, data.get('message'))
                    else:
                        self.log_result(f"Upload {filename}", False, f"Status: {response.status_code}")
                
                except Exception as e:
                    self.log_result(f"Upload {filename}", False, str(e))
    
    def test_file_list(self):
        """Test file listing."""
        self.print_subheader("File Listing")
        
        if not self.auth_tokens:
            self.print_warning("No authenticated users. Skipping file list tests.")
            return
        
        for username, token in self.auth_tokens.items():
            try:
                response = requests.get(
                    f"{self.base_url}/storage/list",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data['status'] == 'success':
                        files = data['data']['files']
                        self.log_result(
                            f"List files ({username})", True,
                            f"Found {len(files)} files"
                        )
                    else:
                        self.log_result(f"List files ({username})", False, data.get('message'))
                else:
                    self.log_result(f"List files ({username})", False, f"Status: {response.status_code}")
            
            except Exception as e:
                self.log_result(f"List files ({username})", False, str(e))
    
    def test_file_download(self):
        """Test file download."""
        self.print_subheader("File Download")
        
        if not self.auth_tokens:
            self.print_warning("No authenticated users. Skipping file download tests.")
            return
        
        # First get list of files
        for username, token in self.auth_tokens.items():
            try:
                # Get file list first
                list_response = requests.get(
                    f"{self.base_url}/storage/list",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if list_response.status_code != 200:
                    self.print_warning(f"Could not list files for {username}")
                    continue
                
                files = list_response.json()['data']['files']
                
                if not files:
                    self.print_warning(f"No files available to download for {username}")
                    continue
                
                # Download first file
                file_id = files[0]['file_id']
                filename = files[0]['name']
                
                response = requests.get(
                    f"{self.base_url}/storage/download/{file_id}",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code == 200:
                    self.log_result(f"Download {filename}", True, f"Downloaded {len(response.content)} bytes")
                else:
                    self.log_result(f"Download {filename}", False, f"Status: {response.status_code}")
            
            except Exception as e:
                self.log_result(f"File download ({username})", False, str(e))
    
    def test_file_delete(self):
        """Test file deletion."""
        self.print_subheader("File Deletion")
        
        if not self.auth_tokens:
            self.print_warning("No authenticated users. Skipping file delete tests.")
            return
        
        for username, token in self.auth_tokens.items():
            try:
                # Get file list first
                list_response = requests.get(
                    f"{self.base_url}/storage/list",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if list_response.status_code != 200:
                    continue
                
                files = list_response.json()['data']['files']
                
                if not files:
                    self.print_warning(f"No files available to delete for {username}")
                    continue
                
                # Delete first file
                file_id = files[0]['file_id']
                filename = files[0]['name']
                
                response = requests.delete(
                    f"{self.base_url}/storage/{file_id}",
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code == 200:
                    self.log_result(f"Delete {filename}", True)
                else:
                    self.log_result(f"Delete {filename}", False, f"Status: {response.status_code}")
            
            except Exception as e:
                self.log_result(f"File deletion ({username})", False, str(e))
    
    def test_error_handling(self):
        """Test error handling."""
        self.print_subheader("Error Handling")
        
        # Test invalid token
        try:
            response = requests.get(
                f"{self.base_url}/storage/list",
                headers={"Authorization": "Bearer invalid_token"}
            )
            
            if response.status_code == 401:
                self.log_result("Invalid token rejection", True)
            else:
                self.log_result("Invalid token rejection", False, f"Expected 401, got {response.status_code}")
        except Exception as e:
            self.log_result("Invalid token rejection", False, str(e))
        
        # Test missing auth header
        try:
            response = requests.get(f"{self.base_url}/storage/list")
            
            if response.status_code == 401:
                self.log_result("Missing auth header rejection", True)
            else:
                self.log_result("Missing auth header rejection", False, f"Expected 401, got {response.status_code}")
        except Exception as e:
            self.log_result("Missing auth header rejection", False, str(e))
        
        # Test invalid endpoint
        try:
            response = requests.get(f"{self.base_url}/invalid/endpoint")
            
            if response.status_code == 404:
                self.log_result("Invalid endpoint handling", True)
            else:
                self.log_result("Invalid endpoint handling", False, f"Expected 404, got {response.status_code}")
        except Exception as e:
            self.log_result("Invalid endpoint handling", False, str(e))
    
    def print_summary(self):
        """Print test summary."""
        self.print_header("TEST SUMMARY")
        
        print(f"Total Tests: {self.total_tests}")
        print(f"{Colors.OKGREEN}Passed: {self.passed_tests}{Colors.ENDC}")
        print(f"{Colors.FAIL}Failed: {self.failed_tests}{Colors.ENDC}")
        
        if self.total_tests > 0:
            pass_rate = (self.passed_tests / self.total_tests) * 100
            print(f"Pass Rate: {pass_rate:.1f}%")
        
        print("\n" + "="*70)
        
        if self.failed_tests == 0:
            print(f"\n{Colors.OKGREEN}{Colors.BOLD}✓ ALL TESTS PASSED!{Colors.ENDC}\n")
        else:
            print(f"\n{Colors.FAIL}{Colors.BOLD}✗ Some tests failed. See details above.{Colors.ENDC}\n")
    
    def run_all_tests(self):
        """Run all tests."""
        self.print_header("CLOUD STORAGE SYSTEM TEST SUITE")
        
        print(f"Backend URL: {self.base_url}")
        print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Run tests in sequence
        self.test_health_check()
        self.test_registration()
        self.test_login_and_otp()
        self.test_account_info()
        self.test_quota_info()
        self.test_file_upload()
        self.test_file_list()
        self.test_file_download()
        self.test_file_delete()
        self.test_error_handling()
        
        # Print summary
        self.print_summary()
        
        return self.failed_tests == 0

if __name__ == "__main__":
    suite = TestSuite()
    success = suite.run_all_tests()
    sys.exit(0 if success else 1)
