import os, math, time, requests, numpy as np, pandas as pd
BOT_TOKEN=os.getenv('BOT_TOKEN'); CHAT_ID=os.getenv('CHAT_ID')
MARKET=os.getenv('MARKET','futures').strip().lower()
INTERVAL=os.getenv('INTERVAL','5m').strip()
LONG_HRS=float(os.getenv('LONG_HRS','96'))
RECENT_HRS=float(os.getenv('RECENT_HRS','3'))
TOPK=int(os.getenv('TOPK','12'))
QUOTE=os.getenv('QUOTE','USDT').strip().upper()
MAX_SYMBOLS=int(os.getenv('MAX_SYMBOLS','150'))
VOL24_MIN_Q=float(os.getenv('VOL24_MIN_Q','50000000'))
LONG_RANGE_MIN_PCT=float(os.getenv('LONG_RANGE_MIN_PCT','15.0'))
LONG_SLOPE_MAX_PCT=float(os.getenv('LONG_SLOPE_MAX_PCT','0.60'))
LONG_Q_LOW=float(os.getenv('LONG_Q_LOW','0.10'))
LONG_Q_HIGH=float(os.getenv('LONG_Q_HIGH','0.90'))
LONG_CONTAIN_MIN=float(os.getenv('LONG_CONTAIN_MIN','0.65'))
RECENT_ATR_MIN_PCT=float(os.getenv('RECENT_ATR_MIN_PCT','0.60'))
RECENT_TOUCH_MIN=int(os.getenv('RECENT_TOUCH_MIN','10'))
RECENT_ALT_MIN=int(os.getenv('RECENT_ALT_MIN','6'))
RECENT_CONTAIN_MIN=float(os.getenv('RECENT_CONTAIN_MIN','0.70'))
TOUCH_EPS_PCT=float(os.getenv('TOUCH_EPS_PCT','0.25'))
GRID_COUNT=int(os.getenv('GRID_COUNT','12'))
assert BOT_TOKEN and CHAT_ID
TG_URL=f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
def send(t):
 import requests
 try:
  requests.post(TG_URL,json={'chat_id':CHAT_ID,'text':t[:3900],'disable_web_page_preview':True},timeout=20)
 except Exception:
  pass
SPOT_BASES=['https://data.binance.com','https://api1.binance.com','https://api2.binance.com','https://api3.binance.com','https://api.binance.com']
FUT_BASES=['https://fapi1.binance.com','https://fapi2.binance.com','https://fapi3.binance.com','https://fapi.binance.com']
def bget(path, params=None, market='spot', timeout=25):
 import requests
 bases=SPOT_BASES if market=='spot' else FUT_BASES
 last=None
 for base in bases:
  try:
   r=requests.get(base+path,params=params,timeout=timeout)
   if r.status_code in (451,403):
    continue
   r.raise_for_status()
   return r.json()
  except Exception as e:
   last=e
   continue
 if last:
  raise last
def uni_symbols(market,quote='USDT'):
 data=bget('/fapi/v1/exchangeInfo',market='futures') if market=='futures' else bget('/api/v3/exchangeInfo',market='spot')
 syms=[]
 for s in data['symbols']:
  if s.get('status')!='TRADING':
   continue
  if s.get('quoteAsset')!=quote:
   continue
  if market=='futures' and s.get('contractType') not in ('PERPETUAL','CURRENT_QUARTER','NEXT_QUARTER'):
   continue
  if any(x in s['symbol'] for x in ('UP','DOWN','BULL','BEAR')):
   continue
  syms.append(s['symbol'])
 return syms
def top_by_quote(symbols,market,topn,volmin):
 path='/api/v3/ticker/24hr' if market=='spot' else '/fapi/v1/ticker/24hr'
 stats=bget(path,market=('spot' if market=='spot' else 'futures'))
 S=set(symbols); rows=[]
 for d in stats:
  sym=d.get('symbol')
  if sym not in S:
   continue
  try:
   q=float(d.get('quoteVolume',0)); last=float(d.get('lastPrice',0))
  except Exception:
   continue
  if q>=volmin and last>0:
   rows.append((sym,q))
 rows.sort(key=lambda x:x[1],reverse=True)
 return [s for s,_ in rows[:topn]]
def bars_for_hours(interval,hours):
 m={'1m':1,'3m':3,'5m':5,'15m':15,'30m':30,'1h':60}.get(interval,5)
 need=int((hours*60)/m)+2
 return min(max(need,60),1000)
def klines(symbol,interval,market,hours):
 L=bars_for_hours(interval,hours)
 data=bget('/fapi/v1/klines',params={'symbol':symbol,'interval':interval,'limit':L},market='futures') if market=='futures' else bget('/api/v3/klines',params={'symbol':symbol,'interval':interval,'limit':L},market='spot')
 if not data:
  return None
 h=np.array([float(x[2]) for x in data]); l=np.array([float(x[3]) for x in data]); c=np.array([float(x[4]) for x in data])
 return h,l,c
def slope_pct(c):
 y=c; import numpy as np
 x=np.arange(len(y)); x=x-x.mean(); m=np.polyfit(x,y,1)[0]; drift=m*(len(y)/2.0)
 import numpy as np
 return float(abs(drift)/np.mean(y)*100.0)
def atr_pct(h,l,c,period=14):
 import numpy as np, pandas as pd
 prev=np.r_[c[0],c[:-1]]; tr=np.maximum(h-l,np.maximum(abs(h-prev),abs(l-prev)))
 atr=pd.Series(tr).rolling(period,min_periods=period//2).mean().iloc[-period:].mean()
 return float(atr/(c[-period:].mean()+1e-12)*100.0)
def band_features(c,q_low,q_high,eps):
 import numpy as np
 low=float(np.quantile(c,q_low)); high=float(np.quantile(c,q_high)); mid=float(np.median(c))
 inside=float(np.logical_and(c>=low,c<=high).mean())
 eps_top=high*(1-eps/100.0); eps_bot=low*(1+eps/100.0)
 top=(c>=eps_top).astype(int); bot=(c<=eps_bot).astype(int)
 touches=int(top.sum()+bot.sum())
 seq=[1 if t and not b else (-1 if b and not t else 0) for t,b in zip(top,bot)]
 seq=[s for s in seq if s!=0]; alts=sum(1 for i in range(1,len(seq)) if seq[i]!=seq[i-1])
 rng=(c.max()-c.min())/max(np.median(c),1e-12)*100.0
 return low,mid,high,inside,touches,alts,rng
def analyze(sym):
 hl=klines(sym,INTERVAL,MARKET,LONG_HRS)
 if not hl: return None
 hL,lL,cL=hl
 lowL,midL,highL,insideL,touchL,altL,rangeL=band_features(cL,LONG_Q_LOW,LONG_Q_HIGH,TOUCH_EPS_PCT)
 sL=slope_pct(cL)
 okR=(rangeL>=LONG_RANGE_MIN_PCT) and (sL<=LONG_SLOPE_MAX_PCT) and (insideL>=LONG_CONTAIN_MIN)
 hs=klines(sym,INTERVAL,MARKET,RECENT_HRS)
 if not hs: return None
 hS,lS,cS=hs
 lowS,midS,highS,insideS,touchS,altS,rangeS=band_features(cS,0.15,0.85,TOUCH_EPS_PCT)
 sS=slope_pct(cS); aS=atr_pct(hS,lS,cS,14)
 okA=(insideS>=RECENT_CONTAIN_MIN) and (aS>=RECENT_ATR_MIN_PCT) and (touchS>=RECENT_TOUCH_MIN) and (altS>=RECENT_ALT_MIN)
 score=(0.4*rangeL + 0.2*insideL*100 + 0.1*touchL + 0.1*altL - 0.3*sL + 0.3*aS + 0.2*touchS + 0.2*altS + 0.2*insideS*100 - 0.3*sS)
 return {'symbol':sym,'regime':okR,'activation':okA,'score':float(score),'long_range':float(rangeL),'long_inside':float(insideL),'long_slope':float(sL),'recent_inside':float(insideS),'recent_touch':int(touchS),'recent_alt':int(altS),'recent_atr':float(aS),'recent_slope':float(sS),'grid_low':float(lowL),'grid_mid':float(midL),'grid_high':float(highL)}
def run():
 syms=uni_symbols(MARKET,QUOTE); pool=top_by_quote(syms,MARKET,MAX_SYMBOLS,VOL24_MIN_Q)
 if not pool:
  send('⚠️ Pro Grid Finder: evrende sembol yok.'); return
 rows=[]
 for s in pool:
  try:
   d=analyze(s)
   if d: rows.append(d)
  except Exception:
   pass
 if not rows:
  send('⚠️ Pro Grid Finder: veri toplanamadı.'); return
 picks=[r for r in rows if r['regime'] and r['activation']]; picks.sort(key=lambda x:x['score'],reverse=True)
 top=picks[:TOPK] if picks else rows[:TOPK]
 hdr=(f'🧰 Pro Grid Box Finder ({MARKET.upper()}) — {INTERVAL} | Regime {int(LONG_HRS)}h + Activation {int(RECENT_HRS)}h\n'
      f'Regime: range≥{LONG_RANGE_MIN_PCT}%, slope≤{LONG_SLOPE_MAX_PCT}%, inside≥{LONG_CONTAIN_MIN} | '
      f'Activation: ATR≥{RECENT_ATR_MIN_PCT}%, touches≥{RECENT_TOUCH_MIN}, alt≥{RECENT_ALT_MIN}, inside≥{RECENT_CONTAIN_MIN}')
 lines=[]
 for r in top:
  tag='✅' if r['regime'] and r['activation'] else '—'
  lines.append(f"{tag} {r['symbol']:<10} | Lrng {r['long_range']:.1f}% Lins {r['long_inside']*100:.0f}% Lsl {r['long_slope']:.2f}% | Ratr {r['recent_atr']:.2f}% Rins {r['recent_inside']*100:.0f}% Rsl {r['recent_slope']:.2f}% T{r['recent_touch']} A{r['recent_alt']} | grid [{r['grid_low']:.6g} … {r['grid_high']:.6g}] mid {r['grid_mid']:.6g} | score {r['score']:.1f}")
 send(hdr+'\n'+"\n".join(lines))
if __name__=='__main__':
 run()