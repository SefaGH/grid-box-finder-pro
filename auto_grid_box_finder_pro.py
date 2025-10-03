
import os, math, time, statistics
import numpy as np, pandas as pd, requests

BOT_TOKEN = os.getenv("BOT_TOKEN"); CHAT_ID = os.getenv("CHAT_ID")
INTERVAL = os.getenv("INTERVAL","5m").strip()
LONG_HRS = float(os.getenv("LONG_HRS","96"))
RECENT_HRS = float(os.getenv("RECENT_HRS","3"))
TOPK = int(os.getenv("TOPK","12"))
QUOTE = os.getenv("QUOTE","USDT").strip().upper()
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS","150"))
VOL24_MIN_Q = float(os.getenv("VOL24_MIN_Q","30000000"))
LONG_RANGE_MIN_PCT = float(os.getenv("LONG_RANGE_MIN_PCT","18.0"))
LONG_SLOPE_MAX_PCT = float(os.getenv("LONG_SLOPE_MAX_PCT","0.50"))
LONG_Q_LOW = float(os.getenv("LONG_Q_LOW","0.10"))
LONG_Q_HIGH = float(os.getenv("LONG_Q_HIGH","0.90"))
LONG_CONTAIN_MIN = float(os.getenv("LONG_CONTAIN_MIN","0.68"))
RECENT_ATR_MIN_PCT = float(os.getenv("RECENT_ATR_MIN_PCT","0.60"))
RECENT_TOUCH_MIN = int(os.getenv("RECENT_TOUCH_MIN","10"))
RECENT_ALT_MIN = int(os.getenv("RECENT_ALT_MIN","6"))
RECENT_CONTAIN_MIN = float(os.getenv("RECENT_CONTAIN_MIN","0.70"))
TOUCH_EPS_PCT = float(os.getenv("TOUCH_EPS_PCT","0.25"))
GRID_COUNT = int(os.getenv("GRID_COUNT","12"))
S_ALT_RATIO_MIN = float(os.getenv("S_ALT_RATIO_MIN","0.70"))
S_TOUCH_BAL_MAX = float(os.getenv("S_TOUCH_BAL_MAX","0.20"))
S_ATR_CV_MAX    = float(os.getenv("S_ATR_CV_MAX","0.25"))
S_DRIFT_MAX_PCT = float(os.getenv("S_DRIFT_MAX_PCT","0.25"))
S_INSIDE_REC_MIN= float(os.getenv("S_INSIDE_REC_MIN","0.78"))

SHOW_ONLY_S = os.getenv("SHOW_ONLY_S","1").strip() not in ("0","false","False")
SHOW_INCLUDE_NEAR = os.getenv("SHOW_INCLUDE_NEAR","0").strip() in ("1","true","True")

assert BOT_TOKEN and CHAT_ID
TG_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
HEADERS = {"Accept":"application/json","User-Agent":"grid-okx-s-only/1.0"}

def send(msg: str):
    try:
        requests.post(TG_URL, json={"chat_id": CHAT_ID, "text": msg[:3900], "disable_web_page_preview": True}, timeout=20)
    except: pass

def okx_get(path, params=None, tries=5, sleep=0.8):
    last=None
    for _ in range(tries):
        try:
            r=requests.get("https://www.okx.com"+path, params=params, headers=HEADERS, timeout=25)
            if r.status_code>=500: time.sleep(sleep); continue
            j=r.json()
            if j.get("code") not in ("0",0):
                last=RuntimeError(f"okx code {j.get('code')}")
                time.sleep(sleep); continue
            return j
        except Exception as e:
            last=e; time.sleep(sleep); continue
    if last: raise last
    raise RuntimeError("okx no response")

def okx_symbols_usdt_swap():
    out=[]
    data=okx_get("/api/v5/public/instruments", params={"instType":"SWAP"})
    for it in data["data"]:
        instId=it.get("instId","")
        if instId.endswith("-USDT-SWAP"): out.append(instId)
    return out

def okx_top_by_turnover(symbols, topn, volmin):
    data=okx_get("/api/v5/market/tickers", params={"instType":"SWAP"})
    S=set(symbols); rows=[]
    for it in data["data"]:
        s=it.get("instId"); 
        if s not in S: continue
        try:
            q=float(it.get("volCcy24h","0")); last=float(it.get("last","0"))
        except: 
            continue
        if q>=volmin and last>0: rows.append((s,q))
    rows.sort(key=lambda x:x[1], reverse=True)
    return [s for s,_ in rows[:topn]]

def bars_for_hours(interval, hours):
    mult={"1m":1,"3m":3,"5m":5,"15m":15,"30m":30,"1h":60}
    mins=mult.get(interval,5)
    need=int(__import__('math').ceil(hours*60/mins))+2
    return min(max(need,60), 1000)

def okx_bar(interval):
    mapping={"1m":"1m","3m":"3m","5m":"5m","15m":"15m","30m":"30m","1h":"1H","2h":"2H","4h":"4H"}
    return mapping.get(interval, "5m")

def klines_okx(instId, interval, hours):
    limit=bars_for_hours(interval, hours)
    params={"instId":instId,"bar":okx_bar(interval),"limit":min(100,limit)}
    data=okx_get("/api/v5/market/candles", params=params)
    lst=data.get("data",[])
    if not lst: return None
    lst.sort(key=lambda x:int(x[0]))
    import numpy as np
    h=np.array([float(x[2]) for x in lst])
    l=np.array([float(x[3]) for x in lst])
    c=np.array([float(x[4]) for x in lst])
    return h,l,c

def slope_pct(closes):
    import numpy as np
    y=closes; x=np.arange(len(y)); x=x-x.mean()
    m=np.polyfit(x,y,1)[0]; drift=m*(len(y)/2.0)
    return float(abs(drift)/np.mean(y)*100.0)

def atr_pct(h,l,c,period=14):
    import numpy as np, pandas as pd
    prev=np.r_[c[0],c[:-1]]
    tr=np.maximum(h-l, np.maximum(np.abs(h-prev), np.abs(l-prev)))
    atr=pd.Series(tr).rolling(period, min_periods=period//2).mean().iloc[-period:].mean()
    return float(atr/(c[-period:].mean()+1e-12)*100.0)

def band_features(closes, q_low, q_high, eps_pct):
    import numpy as np
    low=float(np.quantile(closes,q_low)); high=float(np.quantile(closes,q_high)); mid=float(np.median(closes))
    inside=float(np.logical_and(closes>=low, closes<=high).mean())
    eps_top=high*(1-eps_pct/100.0); eps_bot=low*(1+eps_pct/100.0)
    top=(closes>=eps_top).astype(int); bot=(closes<=eps_bot).astype(int)
    touches=int(top.sum()+bot.sum())
    seq=[1 if t and not b else (-1 if b and not t else 0) for t,b in zip(top,bot)]
    seq=[s for s in seq if s!=0]
    alts=sum(1 for i in range(1,len(seq)) if seq[i]!=seq[i-1])
    rng=(closes.max()-closes.min())/max(np.median(closes),1e-12)*100.0
    top_cnt=int(top.sum()); bot_cnt=int(bot.sum())
    return low,mid,high,inside,touches,alts,rng, top_cnt, bot_cnt

def atr_cv(closes, segment=20):
    import numpy as np
    c=closes; prev=np.r_[c[0],c[:-1]]; tr=np.abs(c-prev)
    N=len(tr)//segment
    if N<3: return 1.0
    chunks=[tr[i*segment:(i+1)*segment].mean() for i in range(N)]
    mu=sum(chunks)/len(chunks); 
    if mu==0: return 1.0
    sd=(sum((x-mu)**2 for x in chunks)/max(len(chunks)-1,1))**0.5
    return float(sd/mu)

def s_pattern_metrics(closes, q_low=0.2, q_high=0.8, eps_pct=0.3):
    low,mid,high,inside,touches,alts,_, top_cnt, bot_cnt = band_features(closes,q_low,q_high,eps_pct)
    alt_ratio = (alts/max(touches-1,1)) if touches>1 else 0.0
    touch_bal = (abs(top_cnt-bot_cnt)/float(touches)) if touches>0 else 1.0
    drift = slope_pct(closes)
    cv = atr_cv(closes, segment=20)
    return {"inside":inside, "touches":touches, "alts":alts, "alt_ratio":alt_ratio,
            "touch_bal":touch_bal, "drift":drift, "atr_cv":cv,
            "band_low":low, "band_mid":mid, "band_high":high}

def analyze(instId):
    hL,lL,cL=klines_okx(instId, INTERVAL, LONG_HRS) or (None,None,None)
    if cL is None: return None
    lowL,midL,highL,insideL,touchL,altL,rangeL,_,_=band_features(cL,LONG_Q_LOW,LONG_Q_HIGH,TOUCH_EPS_PCT)
    slopeL=slope_pct(cL)
    ok_regime=(rangeL>=LONG_RANGE_MIN_PCT) and (slopeL<=LONG_SLOPE_MAX_PCT) and (insideL>=LONG_CONTAIN_MIN)

    hS,lS,cS=klines_okx(instId, INTERVAL, RECENT_HRS) or (None,None,None)
    if cS is None: return None
    lowS,midS,highS,insideS,touchS,altS,rangeS,topS,botS=band_features(cS,0.15,0.85,TOUCH_EPS_PCT)
    slopeS=slope_pct(cS); atrS=atr_pct(hS,lS,cS,period=14)
    ok_activation=(insideS>=RECENT_CONTAIN_MIN) and (atrS>=RECENT_ATR_MIN_PCT) and (touchS>=RECENT_TOUCH_MIN) and (altS>=RECENT_ALT_MIN)

    sp=s_pattern_metrics(cS, q_low=0.2, q_high=0.8, eps_pct=TOUCH_EPS_PCT)
    ok_s=(sp["alt_ratio"]>=S_ALT_RATIO_MIN) and (sp["touch_bal"]<=S_TOUCH_BAL_MAX) and (sp["atr_cv"]<=S_ATR_CV_MAX) and (sp["drift"]<=S_DRIFT_MAX_PCT) and (sp["inside"]>=S_INSIDE_REC_MIN)

    tag="✅ S-GRID" if (ok_regime and ok_activation and ok_s) else ("⚠️ NEAR" if (ok_regime and ok_s) else "—")
    score=(0.35*rangeL + 0.15*insideL*100 - 0.25*slopeL
           + 0.25*atrS + 0.20*touchS + 0.20*altS + 0.20*insideS*100 - 0.25*slopeS
           + 10.0*sp["alt_ratio"] - 8.0*sp["touch_bal"] + 6.0*(1.0 - min(sp["atr_cv"],1.0)) + 4.0*(sp["inside"]))

    return {"symbol":instId,"tag":tag,"regime":ok_regime,"activation":ok_activation,"s_ok":ok_s,"score":float(score),
            "long_range":float(rangeL),"long_inside":float(insideL),"long_slope":float(slopeL),
            "recent_inside":float(insideS),"recent_touch":int(touchS),"recent_alt":int(altS),
            "recent_atr":float(atrS),"recent_slope":float(slopeS),
            "grid_low":float(lowL),"grid_mid":float(midL),"grid_high":float(highL),
            "s_alt_ratio":float(sp["alt_ratio"]),"s_touch_bal":float(sp["touch_bal"]),
            "s_atr_cv":float(sp["atr_cv"]),"s_drift":float(sp["drift"])}

def run():
    syms=okx_symbols_usdt_swap()
    pool=okx_top_by_turnover(syms, MAX_SYMBOLS, VOL24_MIN_Q)
    rows=[]
    for s in pool:
        try:
            d=analyze(s)
            if d: rows.append(d)
        except: pass

    sgrid=[r for r in rows if r["tag"]=="✅ S-GRID"]
    near=[r for r in rows if r["tag"]=="⚠️ NEAR"]
    sgrid.sort(key=lambda x:x["score"], reverse=True)
    near.sort(key=lambda x:x["score"], reverse=True)

    if SHOW_ONLY_S:
        picks=sgrid[:TOPK]
        title_tag="ONLY S-GRID"
        if not picks and SHOW_INCLUDE_NEAR:
            picks=near[:TOPK]; title_tag="ONLY NEAR"
    else:
        picks=(sgrid+near)[:TOPK] if (sgrid or near) else sorted(rows, key=lambda x:x["score"], reverse=True)[:TOPK]
        title_tag="S+NEAR or fallback"

    hdr=(f"🧰 Pro Grid Box Finder — OKX (USDT swap) — {INTERVAL} | Regime {int(LONG_HRS)}h + Activation {int(RECENT_HRS)}h + S-Pattern [{title_tag}]")
    if not picks:
        lines=["(no S-GRID matches)"]
    else:
        lines=[]
        for r in picks:
            lines.append(f"{r['tag']} {r['symbol']:<16} | Lrng {r['long_range']:.1f}% Lins {r['long_inside']*100:.0f}% Lsl {r['long_slope']:.2f}% | "
                         f"Ratr {r['recent_atr']:.2f}% Rins {r['recent_inside']*100:.0f}% Rsl {r['recent_slope']:.2f}% "
                         f"T{r['recent_touch']} A{r['recent_alt']} | S altR {r['s_alt_ratio']:.2f} bal {r['s_touch_bal']:.2f} cv {r['s_atr_cv']:.2f} d {r['s_drift']:.2f}% "
                         f"| grid [{r['grid_low']:.6g} … {r['grid_high']:.6g}] mid {r['grid_mid']:.6g} | score {r['score']:.1f}")
    send(hdr + "\n" + "\n".join(lines))

if __name__=="__main__":
    run()
