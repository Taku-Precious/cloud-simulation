#!/usr/bin/env python3
import requests
import sqlite3
import json

conn = sqlite3.connect('auth/auth.db')
cursor = conn.cursor()
cursor.execute('SELECT otp FROM sessions WHERE session_id = ?', ('68a2c1c6-2bd6-4918-81b4-544427b19a5a',))
result = cursor.fetchone()
otp = result[0] if result else None
conn.close()

if otp:
    verify_resp = requests.post('http://localhost:8000/auth/verify-otp', json={
        'session_id': '68a2c1c6-2bd6-4918-81b4-544427b19a5a',
        'username': 'quotatest123',
        'otp': otp
    })
    verify_data = verify_resp.json()
    
    token = verify_data.get('auth_token')
    print(f'Token: {token}')
    
    quota_resp = requests.get('http://localhost:8000/storage/quota', 
                             headers={'Authorization': 'Bearer ' + token})
    print(f'Status: {quota_resp.status_code}')
    print('Quota data:')
    print(json.dumps(quota_resp.json(), indent=2))
