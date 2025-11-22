#!/bin/bash

# Start FastAPI in the background
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# Start Streamlit in the foreground
streamlit run frontend.py --server.port 8501 --server.address 0.0.0.0