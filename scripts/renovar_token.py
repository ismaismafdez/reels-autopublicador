#!/usr/bin/env python3
"""Renueva el token de larga duración de Instagram (60 días). Imprime el token nuevo por stdout."""
import os
import sys

import requests

r = requests.get(
    "https://graph.instagram.com/refresh_access_token",
    params={"grant_type": "ig_refresh_token", "access_token": os.environ["IG_ACCESS_TOKEN"]},
    timeout=60,
)
if r.status_code != 200:
    print(f"Error renovando token: HTTP {r.status_code} {r.text[:300]}", file=sys.stderr)
    sys.exit(1)
print(r.json()["access_token"])
