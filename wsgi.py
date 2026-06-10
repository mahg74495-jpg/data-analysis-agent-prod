#!/usr/bin/env python3
"""WSGI entry point for Gunicorn."""
from api import create_app

app = create_app()
