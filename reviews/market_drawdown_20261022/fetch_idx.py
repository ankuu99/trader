import os, sys, pandas as pd
from datetime import datetime, timedelta
sys.path.insert(0, os.getcwd())
from dotenv import dotenv_values
from kiteconnect import KiteConnect
env = dotenv_values("config/.env")
k = KiteConnect(api_key=env["KITE_API_KEY"]); k.set_access_token(env["KITE_ACCESS_TOKEN"])
ins = {i["tradingsymbol"]: i["instrument_token"] for i in k.instruments("NSE") if i["segment"] == "INDICES"}
out = {}
for name in ["NIFTY SMLCAP 250", "NIFTY MIDCAP 100", "NIFTY 50"]:
    tok = ins[name]; rows = []
    s = datetime(2019, 6, 1)
    while s < datetime.now():
        e = min(s + timedelta(days=1900), datetime.now())
        rows += k.historical_data(tok, s, e, "day"); s = e + timedelta(days=1)
    df = pd.DataFrame(rows)[["date", "close"]]; df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    out[name] = df.set_index("date")["close"]
pd.DataFrame(out).to_csv(sys.argv[1]); print(pd.DataFrame(out).tail(3))
