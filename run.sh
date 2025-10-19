#!/bin/bash
cd ~/garage_manager
source venv/bin/activate
gunicorn app:app --bind 0.0.0.0:8001 --workers 4
