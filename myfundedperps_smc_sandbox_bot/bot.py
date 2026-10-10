import asyncio,json,logging,os
from decimal import Decimal,InvalidOperation
import requests,websockets
from dotenv import load_dotenv

load_dotenv()
KEY=os.getenv("FP_API_KEY","")
ACCOUNT=os.getenv("FP_ACCOUNT_ID","")
BASE="https://sandbox.myfundedperpetuals.com"
WS="wss://api-stream.myfundedperpetuals.com/v1/market-data"
DRY=os.getenv("DRY_RUN","true").lower()!="false"
LOOK=int(os.getenv("SWING_LOOKBACK","10"))
LIMIT=min(24,max(1,int(os.getenv("WATCHLIST_LIMIT","24"))))
PROVIDER=os.getenv("PROVIDER_PREFERENCE","binance").lower()
R=Decimal(os.getenv("TARGET_R_MULTIPLE","1.5"))

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("smc")

def api(path):
    if not KEY.startswith("fp_test_"): raise SystemExit("SAFETY STOP: FP_API_KEY must start with fp_test_.")
    if not ACCOUNT: raise SystemExit("Set FP_ACCOUNT_ID.")
    r=requests.get(BASE+path,headers={"Authorization":f"Bearer {KEY}","Accept":"application/json"},timeout=15)
    r.raise_for_status()
    return r.json()

def markets():
    p=requests.get(BASE+"/v1/markets",timeout=15).json()
    xs=p.get("data",p)
    if isinstance(xs,dict): xs=xs.get("markets",[])
    out=[]
    for m in xs if isinstance(xs,list) else []:
        prov=str(m.get("provider","")).lower()
        sym=m.get("coin") or m.get("venue_symbol") or m.get("symbol")
        mid=m.get("id") or m.get("market_id")
        if prov==PROVIDER and sym and mid and str(m.get("status","active")).lower() not in {"disabled","closed","inactive"}:
            out.append({"symbol":str(sym),"provider":prov,"market_id":str(mid)})
    return out[:LIMIT]

def signal(cs):
    cs=[c for c in sorted(cs,key=lambda x:int(x.get("openTime",0))) if c.get("isFinal")]
    if len(cs)<LOOK+3:return None
    recent=cs[-LOOK-2:-2]; prev,cur=cs[-2],cs[-1]
    try:
        hi=max(Decimal(x["high"]) for x in recent); lo=min(Decimal(x["low"]) for x in recent)
        o,h,l,c=[Decimal(cur[k]) for k in ("open","high","low","close")]
        ph,pl=[Decimal(prev[k]) for k in ("high","low")]
        avg=sum(Decimal(x["high"])-Decimal(x["low"]) for x in cs[-7:-1])/Decimal(max(1,len(cs[-7:-1])))
    except (KeyError,InvalidOperation): return None
    disp=avg>0 and abs(c-o)>=avg*Decimal("0.8")
    if l<lo and c>o and disp and c>ph:return ("buy",c,l,"sell-side sweep + bullish displacement + reclaim")
    if h>hi and c<o and disp and c<pl:return ("sell",c,h,"buy-side sweep + bearish displacement + break")
    return None

async def main():
    if not KEY.startswith("fp_test_"): raise SystemExit("Sandbox key required (fp_test_).")
    if not ACCOUNT: raise SystemExit("FP_ACCOUNT_ID is required.")
    if not DRY: raise SystemExit("Execution is disabled in this starter. Keep DRY_RUN=true.")
    acct=api(f"/v1/accounts/{ACCOUNT}")
    ms=markets()
    if not ms: raise SystemExit("No eligible markets discovered.")
    log.info("Sandbox account checked; monitoring %d %s 1m markets.",len(ms),PROVIDER)
    books={(m["symbol"],m["provider"]):[] for m in ms}
    async with websockets.connect(WS,ping_interval=20,ping_timeout=20) as ws:
        for i in range(0,len(ms),24):
            b=ms[i:i+24]
            await ws.send(json.dumps({"op":"sub","id":i//24+1,"channel":"candles","payload":{"symbols":[m["symbol"] for m in b],"providers":[PROVIDER],"intervals":["1m"],"historyLimit":100}}))
        async for raw in ws:
            f=json.loads(raw)
            if f.get("op")!="events": continue
            for e in f.get("events",[]):
                if e.get("type")!="candle" or e.get("interval")!="1m" or not e.get("isFinal"): continue
                k=(e.get("symbol"),str(e.get("provider","")).lower())
                if k not in books: continue
                books[k].append(e); books[k]=books[k][-150:]
                s=signal(books[k])
                if s:
                    side,entry,stop,why=s
                    dist=abs(entry-stop)
                    target=entry+R*dist if side=="buy" else entry-R*dist
                    log.warning("SIGNAL %s %s entry=%s stop=%s target=%s | %s",k[0],side.upper(),entry,stop,target,why)

if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: log.info("Stopped.")
