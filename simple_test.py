#!/usr/bin/env python3
import requests
import json

# First register
reg = requests.post('http://localhost:8000/auth/register', json={
    'username': 'simpletest',
    'email': 'simple@test.com',
    'password': 'Simple@123'
})
print('Register:', reg.status_code)

# Login
login = requests.post('http://localhost:8000/auth/login', json={
    'username': 'simpletest',
    'password': 'Simple@123'
})
login_data = login.json()
session_id = login_data.get('session_id')
print('Login:', login.status_code, 'Session:', session_id)

# Get OTP
import sqlite3
conn = sqlite3.connect('auth/auth.db')
cursor = conn.cursor()
cursor.execute('SELECT otp FROM sessions WHERE session_id = ?', (session_id,))
otp_result = cursor.fetchone()
conn.close()
otp = otp_result[0] if otp_result else None
print('OTP:', otp)

# Verify OTP
verify = requests.post('http://localhost:8000/auth/verify-otp', json={
    'session_id': session_id,
    'username': 'simpletest',
    'otp': otp
})
verify_data = verify.json()
token = verify_data.get('auth_token')
print('Verify:', verify.status_code, 'Token:', token[:20] if token else 'None')

# Test quota
quota = requests.get('http://localhost:8000/storage/quota',
                    headers={'Authorization': f'Bearer {token}'})
print('\nQuota response status:', quota.status_code)
print('Quota response:')
print(json.dumps(quota.json(), indent=2))
