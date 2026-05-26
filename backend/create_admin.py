"""
Create or reset the admin user in MongoDB.

Usage
-----
    python create_admin.py

Run this once after setting up the project, or any time you need to
reset the admin password.  Requires MONGO_URI to be set in .env.

The script will:
  1. Connect to MongoDB using the MONGO_URI in .env
  2. Prompt for a username and password (input is hidden)
  3. Hash the password with bcrypt and upsert the user document
"""

import sys
import getpass
from dotenv import load_dotenv

load_dotenv(override=True)

from auth import create_user, get_user, hash_password
from database.mongo import get_mongo_db


def main():
    print("\n── AuraSafety Admin Setup ──────────────────────────────")

    # Verify MongoDB is reachable
    db = get_mongo_db()
    if db is None:
        print("\n[ERROR] Could not connect to MongoDB.")
        print("  Make sure MONGO_URI is set correctly in backend/.env")
        sys.exit(1)

    print("  MongoDB connected.\n")

    username = input("Admin username [adminMW]: ").strip() or "adminMW"

    while True:
        password = getpass.getpass("Admin password: ")
        if len(password) < 8:
            print("  Password must be at least 8 characters. Try again.")
            continue
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("  Passwords do not match. Try again.")
            continue
        break

    # Upsert — update if exists, create if not
    existing = get_user(username)
    if existing:
        # Update password hash in place
        db["users"].update_one(
            {"username": username},
            {"$set": {"password_hash": hash_password(password)}},
        )
        print(f"\n  Password updated for existing user '{username}'.")
    else:
        ok = create_user(username, password, role="admin")
        if ok:
            print(f"\n  Admin user '{username}' created successfully.")
        else:
            print(f"\n  User '{username}' already exists (race condition). Try again.")
            sys.exit(1)

    print("\n  You can now log in at http://localhost:5173/login")
    print("─" * 55 + "\n")


if __name__ == "__main__":
    main()
