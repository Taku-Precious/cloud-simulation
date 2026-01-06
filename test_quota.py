#!/usr/bin/env python3
import sqlite3
import requests

# Get a token from database
conn = sqlite3.connect('auth/auth.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('Tables:', [t[0] for t in tables])

# Try to get a token from auth_tokens or similar
try:
    cursor.execute("SELECT id, username, token FROM auth_tokens LIMIT 1")
    token_data = cursor.fetchone()
    if token_data:
        print(f'Found token: {token_data}')
        token = token_data[2]
    else:
        print('No tokens found')
except Exception as e:
    print(f'Error querying auth_tokens: {e}')

# Try sessions
try:
    cursor.execute("PRAGMA table_info(sessions)")
    columns = cursor.fetchall()
    print('Sessions columns:', [c[1] for c in columns])
    
    cursor.execute("SELECT * FROM sessions LIMIT 1")
    session = cursor.fetchone()
    if session:
        print(f'First session: {session}')
except Exception as e:
    print(f'Error with sessions: {e}')

conn.close()

# Test login to get a token
print('\n--- Testing login ---')
login_resp = requests.post('http://localhost:8000/auth/login', json={
    'username': 'storagetest001',
    'password': 'Test@1234'
})
print(f'Login status: {login_resp.status_code}')
print(f'Login response: {login_resp.text}')

if login_resp.status_code == 200:
    login_data = login_resp.json()
    session_id = login_data.get('session_id')
    print(f'Session ID: {session_id}')
    
    # Now test quota endpoint with this session
    if session_id:
        # We need to verify OTP first, but let's test the quota with basic auth
        print('\n--- Testing quota (no auth) ---')
        quota_resp = requests.get('http://localhost:8000/storage/quota')
        print(f'Quota status: {quota_resp.status_code}')
        print(f'Quota response: {quota_resp.json() if quota_resp.status_code == 200 else quota_resp.text}')
