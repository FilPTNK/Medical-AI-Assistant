import sys
import os
import uvicorn

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import app
import config

if __name__ == "__main__":
    print(f"[*] Starting MedRetrieve FastAPI Backend on http://{config.HOST}:{config.PORT}", flush=True)
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=False)
