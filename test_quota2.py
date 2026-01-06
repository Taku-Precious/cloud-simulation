#!/usr/bin/env python3
import requests
import sqlite3
import json

# Get the OTP from database
conn = sqlite3.connect('auth/auth.db')
cursor = conn.cursor()
cursor.execute("SELECT otp FROM sessions WHERE session_id = ?", ('68a2c1c6-2bd6-4918-81b4-544427b19a5a',))
result = cursor.fetchone()
otp = result[0] if result else None
conn.close()

print(f'OTP from database: {otp}')

if otp:
    # Verify OTP
    verify_resp = requests.post('http://localhost:8000/auth/verify-otp', json={
        'session_id': '68a2c1c6-2bd6-4918-81b4-544427b19a5a',
        'username': 'quotatest123',
        'otp': otp
    })
    print(f'Verify status: {verify_resp.status_code}')
    verify_data = verify_resp.json()
    print(f'Verify response: {json.dumps(verify_data, indent=2)}')
    
    if 'token' in verify_data:
        token = verify_data['token']
        print(f'\nToken received: {token[:30]}...')
        
        # Now test quota with this token
        print(f'\nTesting quota with token...')
        quota_resp = requests.get('http://localhost:8000/storage/quota', 
                                 headers={'Authorization': f'Bearer {token}'})
        print(f'Quota status: {quota_resp.status_code}')
        quota_data = quota_resp.json()
        print(f'Quota response: {json.dumps(quota_data, indent=2)}')
