#!/usr/bin/env python3
"""Set the reboot/shutdown login for the Pi monitor dashboard.

Run interactively on the Pi:  python3 set_power_password.py
Writes a salted PBKDF2 hash to ./power_auth (chmod 600). No plaintext stored.
"""
import getpass
import hashlib
import json
import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_FILE = os.path.join(BASE_DIR, "power_auth")

user = input("Power username: ").strip()
if not user:
    raise SystemExit("username cannot be empty")
pw = getpass.getpass("Power password: ")
if len(pw) < 6:
    raise SystemExit("use at least 6 characters")
if pw != getpass.getpass("Confirm password: "):
    raise SystemExit("passwords do not match")

salt = secrets.token_bytes(16)
iterations = 200_000
digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iterations)

with open(AUTH_FILE, "w") as f:
    json.dump(
        {"user": user, "iter": iterations, "salt": salt.hex(), "hash": digest.hex()}, f
    )
os.chmod(AUTH_FILE, 0o600)
print(f"Saved {AUTH_FILE} (user '{user}'). Reboot/shutdown buttons are now active.")
