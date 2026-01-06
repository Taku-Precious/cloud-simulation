"""
Test script to verify unified server stays running when client disconnects.
This script tests client operations WITHOUT killing the server.
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

# Import protobuf and client
import cloudsecurity_pb2
import cloudsecurity_pb2_grpc
from auth.client import CloudSecurityClient

def test_login_and_disconnect():
    """Test that server stays running after client disconnects."""
    print("\n" + "=" * 70)
    print("TEST: Client connects, logs in, and disconnects")
    print("=" * 70)
    
    try:
        # Create client and connect
        client = CloudSecurityClient()
        if not client.connect():
            print("❌ Failed to connect to server")
            return False
        
        print("✓ Connected to server")
        
        # Attempt to register a test user
        print("\n[1] Attempting to register test user...")
        try:
            response = client.stub.login(
                cloudsecurity_pb2.Request(
                    login="__REGISTER__",
                    password="REGISTER|testuser456|test456@example.com|TestPass123!"
                )
            )
            
            if "REG_SUCCESS" in response.result or "already exists" in response.result:
                print(f"✓ Registration handled: {response.result[:60]}...")
            else:
                print(f"⚠ Registration response: {response.result[:60]}...")
        except Exception as e:
            print(f"⚠ Registration attempt error: {e}")
        
        # Now test login
        print("\n[2] Attempting to login...")
        try:
            success, message, session_id = client.login("testuser456", "TestPass123!")
            
            if success:
                print(f"✓ Login successful: {message}")
                print(f"  Session ID: {session_id[:20]}...")
            else:
                print(f"⚠ Login response: {message[:60]}...")
        except Exception as e:
            print(f"⚠ Login attempt error: {e}")
        
        print("\n[3] Disconnecting client gracefully...")
        time.sleep(1)  # Give time for any pending operations
        client.disconnect()
        print("✓ Client disconnected")
        
        return True
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multiple_clients():
    """Test multiple clients connecting and disconnecting."""
    print("\n" + "=" * 70)
    print("TEST: Multiple clients connect and disconnect")
    print("=" * 70)
    
    try:
        clients = []
        
        # Create and connect multiple clients
        for i in range(3):
            print(f"\n[Client {i+1}] Connecting...")
            client = CloudSecurityClient()
            if client.connect():
                print(f"✓ Client {i+1} connected")
                clients.append(client)
            else:
                print(f"❌ Client {i+1} failed to connect")
                # Disconnect already-connected clients
                for c in clients:
                    c.disconnect()
                return False
        
        print(f"\n✓ All {len(clients)} clients connected")
        
        # Disconnect each client
        print("\nDisconnecting clients...")
        for i, client in enumerate(clients):
            client.disconnect()
            print(f"✓ Client {i+1} disconnected")
            time.sleep(0.5)
        
        return True
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_server_persistence():
    """Test that server is still running after client operations."""
    print("\n" + "=" * 70)
    print("TEST: Verify server is still running")
    print("=" * 70)
    
    try:
        print("\nAttempting to connect to server...")
        time.sleep(2)  # Wait for any cleanup
        
        client = CloudSecurityClient()
        if client.connect():
            print("✓ Server is still running! Can connect successfully.")
            client.disconnect()
            return True
        else:
            print("❌ Server appears to be down - cannot connect")
            return False
    except Exception as e:
        print(f"❌ Connection test error: {e}")
        return False


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("PERSISTENT CLIENT TEST SUITE")
    print("Testing that server stays running when clients disconnect")
    print("=" * 70)
    
    try:
        # Run tests
        test1_passed = test_login_and_disconnect()
        test2_passed = test_multiple_clients()
        test3_passed = test_server_persistence()
        
        # Summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        print(f"Test 1 (Login & Disconnect):   {'✓ PASSED' if test1_passed else '❌ FAILED'}")
        print(f"Test 2 (Multiple Clients):     {'✓ PASSED' if test2_passed else '❌ FAILED'}")
        print(f"Test 3 (Server Persistence):   {'✓ PASSED' if test3_passed else '❌ FAILED'}")
        print("=" * 70)
        
        all_passed = test1_passed and test2_passed and test3_passed
        if all_passed:
            print("\n✓ All tests passed! Server is persistent across client disconnections.")
            sys.exit(0)
        else:
            print("\n⚠ Some tests did not complete successfully")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
