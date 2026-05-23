from dotenv import load_dotenv
import os, smtplib

load_dotenv()

p = os.getenv('SMTP_PASSWORD', '')
u = os.getenv('SMTP_USER', '')
h = os.getenv('SMTP_HOST', 'smtp.gmail.com')
port = int(os.getenv('SMTP_PORT', '587'))

print(f"User      : {u}")
print(f"Password length : {len(p)}")
print(f"Has spaces      : {' ' in p}")
print(f"Has quotes      : {chr(34) in p or chr(39) in p}")
print(f"Starts with     : {repr(p[:4])}")
print(f"Ends with       : {repr(p[-4:])}")
print(f"Raw repr        : {repr(p)}")
print()

# Try auth directly
try:
    with smtplib.SMTP(h, port, timeout=10) as s:
        s.ehlo()
        s.starttls()
        s.login(u, p)
        print("LOGIN SUCCESS")
except smtplib.SMTPAuthenticationError as e:
    print(f"AUTH FAILED: {e}")
    print()
    print("Common causes:")
    print("  1. Password has spaces — remove them (App Password is 16 chars, no spaces)")
    print("  2. Still using account password — must use App Password")
    print("  3. 2FA not enabled on the Google account")
    print("  4. App Password was generated for wrong account")
except Exception as e:
    print(f"OTHER ERROR: {e}")
