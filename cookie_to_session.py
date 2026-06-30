"""
Convert Instagram cookies to instagrapi session file.

Usage:
    python cookie_to_session.py <account_name> <cookies_file>

Examples:
    python cookie_to_session.py default instagram_cookies.txt
    python cookie_to_session.py myaccount instagram_cookies_myaccount.txt
"""

import sys
from auth import import_cookies


def main():
    if len(sys.argv) < 3:
        print("Usage: python cookie_to_session.py <account_name> <cookies_file>")
        print()
        print("Examples:")
        print("  python cookie_to_session.py default instagram_cookies.txt")
        print("  python cookie_to_session.py myaccount instagram_cookies_myaccount.txt")
        sys.exit(1)

    account = sys.argv[1]
    cookies_file = sys.argv[2]

    try:
        user_id = import_cookies(account, cookies_file)
        print(f"Session saved for account '{account}' (user ID: {user_id})")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
