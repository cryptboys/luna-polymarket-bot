#!/usr/bin/env python3
"""
Generate Polymarket API credentials from private key
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from py_clob_client.client import ClobClient
from dotenv import load_dotenv

load_dotenv()

private_key = os.getenv('POLY_PRIVATE_KEY')

if not private_key:
    print("❌ POLY_PRIVATE_KEY not found in .env")
    sys.exit(1)

print("🔑 Generating API credentials...")
print("⚠️  Make sure your wallet has some MATIC for gas!")

try:
    client = ClobClient(
        host="https://clob.polymarket.com",
        key=private_key,
        chain_id=137  # Polygon
    )
    
    # Generate L2 credentials
    api_creds = client.create_or_derive_api_creds()
    
    print("\n" + "="*50)
    print("✅ API Credentials Generated!")
    print("="*50)
    print(f"API Key: {api_creds.api_key}")
    print(f"Secret: {api_creds.secret}")
    print(f"Passphrase: {api_creds.passphrase}")
    print("="*50)
    print("📝 Copy these to your .env file:")
    print(f"POLY_API_KEY={api_creds.api_key}")
    print(f"POLY_API_SECRET={api_creds.secret}")
    print(f"POLY_PASSPHRASE={api_creds.passphrase}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nPossible issues:")
    print("- Wallet doesn't have MATIC for gas")
    print("- Invalid private key")
    print("- Network issue")
