#!/usr/bin/env python3
"""Genera todos los secretos necesarios para el archivo .env."""

import secrets
import string
from cryptography.fernet import Fernet


def strong_password(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        has_upper = any(c.isupper() for c in pwd)
        has_lower = any(c.islower() for c in pwd)
        has_digit = any(c.isdigit() for c in pwd)
        has_special = any(c in "!@#$%^&*" for c in pwd)
        if has_upper and has_lower and has_digit and has_special:
            return pwd


print("# Copia estos valores a tu archivo .env")
print("# Genera nuevos secretos cada vez que configures un entorno nuevo")
print()
print(f"POSTGRES_PASSWORD={strong_password()}")
print(f"AIRFLOW_PASSWORD={strong_password()}")
print(f"AIRFLOW_FERNET_KEY={Fernet.generate_key().decode()}")
print(f"AIRFLOW_SECRET_KEY={secrets.token_urlsafe(32)}")
print(f"API_SECRET_KEY={secrets.token_urlsafe(48)}")
