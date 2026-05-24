import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request

LOG_PATH = Path(__file__).parent / "logs" / "requests.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI()


@app.post("/approve")
async def approve(request: Request):
    body = await request.json()
    logging.info(json.dumps(body))
    return {"decision": "approve"}
