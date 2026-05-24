#!/bin/bash
cd "$(dirname "$0")"
source ../.venv/bin/activate
pip install -q -r requirements.txt
uvicorn server:app --port 8765
