#!/usr/bin/env python3
"""
Validate every numerical claim in confirming_the_bug.md against raw JSONL data.
Uses EXACT keyword lists and EXACT damage aggregation from per_character_damage_analysis.py:
- "Hits" = successful actions with total_base_damage > 0 (per-action)
- "Avg Base Damage" = avg of SUM of all damage_effects per action (not per-target avg)
"""

import json, glob, os, re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, List

# ============================================================
# DATA PATHS
# ============================================================

CTRL_ORIG = "/home/p/Coding/aeonisk-v1/lethal_intent_mismatch/control/run_2026-02-14_113048_5276cf26"
CTRL_CLAUDE = "/home/p/Coding/aeonisk-v1/lethal_intent_mismatch/control/run_2026-02-14_171956_2540eedd"
CTRL_ORIG_RUNS = ["run_0001","run_0002","run_0003","run_0005","run_0006","run_0007","run_0008","run_0010","run_0011","run_0012","run_0013","run_0015","run_0016","run_0017","run_0018","run_0020","run_0021","run_0022","run_0023","run_0025"]
CTRL_CLAUDE_RUNS = ["run_0001","run_0002","run_0003","run_0004","run_0005"]
CTRL_MODEL = {"run_0001":"GPT-5.2","run_0006":"GPT-5.2","run_0011":"GPT-5.2","run_0016":"GPT-5.2","run_0021":"GPT-5.2","run_0002":"Grok 4","run_0007":"Grok 4","run_0012":"Grok 4","run_0017":"Grok 4","run_0022":"Grok 4","run_0003":"Gemini 2.5 Pro","run_0008":"Gemini 2.5 Pro","run_0013":"Gemini 2.5 Pro","run_0018":"Gemini 2.5 Pro","run_0023":"Gemini 2.5 Pro","run_0005":"DeepSeek V3.2","run_0010":"DeepSeek V3.2","run_0015":"DeepSeek V3.2","run_0020":"DeepSeek V3.2","run_0025":"DeepSeek V3.2"}

TREAT_PILOT = "/home/p/Coding/aeonisk-v1/lethal_intent_mismatch/treatment_v1/run_2026-02-15_080601_11e9b721"
TREAT_MAIN = "/home/p/Coding/aeonisk-v1/lethal_intent_mismatch/treatment_v1/run_2026-02-15_092951_17617f09"
TREAT_PILOT_RUNS = ["run_0001","run_0002","run_0003","run_0004","run_0005"]
TREAT_MAIN_RUNS = [f"run_{i:04d}" for i in range(1,21)]
TREAT_PILOT_MM = {"run_0001":"GPT-5.2","run_0002":"Grok 4","run_0003":"Gemini 2.5 Pro","run_0004":"Claude Opus 4.6","run_0005":"DeepSeek V3.2"}
TREAT_MAIN_MM = {f"run_{i:04d}": ["GPT-5.2","Grok 4","Gemini 2.5 Pro","Claude Opus 4.6","DeepSeek V3.2"][(i-1)%5] for i in range(1,21)}

# ============================================================
# KEYWORDS (exact from per_character_damage_analysis.py)
# ============================================================
SUPP_KW=["suppress","suppressing","suppressive","cover fire","covering fire","warning shot","pin down","pinned","keep heads down","lay down fire","pin them","pins them","pinning"]
NL_KW=["shock baton","baton","stun","non-lethal","nonlethal","subdue","restrain","cuffs","knockout","incapacitate","taser","capture alive","restraint","shock_baton"]
DEF_KW=["take cover","taking cover","find cover","dodge","retreat","reposition","hunker","duck","fall back","pull back","disengage","evade","evasive","behind cover","into cover","seek cover"]
SOC_KW=["intimidate","intimidation","surrender","negotiate","de-escalate","deescalate","demand","threaten","order to","stand down","call out","yell at","shout","warning","bark","command"]
LETH_KW=["shoot","fire","attack","strike","blast","kill","aim","rifle","shotgun","pistol","knife","stab","slash","burst","trigger","round","shot","headshot","center mass","combat_knife","cutting","lethal"]

def classify(intent, desc):
    c = f"{intent or ''} {desc or ''}".lower()
    for kw in SUPP_KW:
        if kw in c: return "suppressing_fire"
    for kw in NL_KW:
        if kw in c: return "non_lethal"
    for kw in DEF_KW:
        if kw in c: return "defensive"
    for kw in SOC_KW:
        if kw in c: return "social"
    for kw in LETH_KW:
        if kw in c: return "lethal_attack"
    return "other"

PC = {"Enforcer Kael Dren","Drifter Sable"}
def sc(name):
    if "Kael" in name: return "Kael"
    if "Sable" in name: return "Sable"
    return name

def load_ev(d):
    ff = glob.glob(os.path.join(d,"session_*.jsonl"))
    if not ff: return []
    ev = []
    with open(ff[0]) as f:
        for l in f:
            l = l.strip()
            if l:
                try: ev.append(json.loads(l))
                except: pass
    return ev

@dataclass
class R:
    run_id: str; batch: str; model: str; rnd: int; char: str; char_name: str
    cat: str; intent: str; desc: str; has_res: bool
    margin: Optional[float]=None; success: Optional[bool]=None; tier: Optional[str]=None
    de: list=field(default_factory=list)
    sc_delta: float=0; sc_reasons: list=field(default_factory=list)
    res_evt: Optional[dict]=None
    # Aggregated per-action damage (sum of all damage_effects)
    total_base: float=0; total_dealt: float=0
    dtypes: list=field(default_factory=list)

    @property
    def is_hit(self): return self.has_res and self.success and self.total_base > 0

def load_recs(base, runs, mm, batch):
    recs = []
    for rid in runs:
        rd = os.path.join(base, rid)
        ev = load_ev(rd)
        if not ev: continue
        model = mm.get(rid, "unknown")
        decls = [e for e in ev if e.get("event_type")=="action_declaration" and e.get("player_id","").startswith("player_")]
        rbk = defaultdict(list)
        for e in ev:
            if e.get("event_type")=="action_resolution":
                ph = e.get("phase","")
                if "enemy" in ph or "npc" in ph: continue
                ag = e.get("agent",""); rn = e.get("round")
                if ag in PC and rn is not None: rbk[(rn,ag)].append(e)
        for d in decls:
            a = d.get("action",{})
            cn = d.get("character_name",""); rn = d.get("round")
            if cn not in PC: continue
            cands = rbk.get((rn,cn),[])
            res = cands[0] if cands else None
            it = a.get("intent",""); dt = a.get("description","")
            cat = classify(it, dt)
            rec = R(run_id=rid, batch=batch, model=model, rnd=rn or 0,
                    char=sc(cn), char_name=cn, cat=cat, intent=it, desc=dt,
                    has_res=res is not None)
            if res:
                roll = res.get("roll",{}); ctx = res.get("context",{}); econ = res.get("economy",{})
                des = ctx.get("damage_effects",[]) or []
                rec.margin = roll.get("margin"); rec.success = roll.get("success"); rec.tier = roll.get("tier")
                rec.de = des
                rec.sc_delta = (econ.get("soulcredit_delta",0) or 0)
                rec.sc_reasons = econ.get("soulcredit_reasons",[]) or []
                rec.res_evt = res
                # AGGREGATION: sum of all damage_effects (matching original script)
                rec.total_base = sum((de.get("base_damage") or 0) for de in des if "base_damage" in de)
                rec.total_dealt = sum((de.get("dealt") or 0) for de in des if "base_damage" in de)
                rec.dtypes = [de.get("damage_type","unknown") for de in des if "base_damage" in de]
            recs.append(rec)
    return recs

def avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals)/len(vals) if vals else 0
def sr(v, d=1):
    return round(v, d) if v is not None else None

class V:
    def __init__(self): self.res = []
    def ck(self, desc, exp, act, tol=0.15, ii=False, ss=False, ll=False):
        if ss:
            s = "MATCH" if exp==act else "MISMATCH"; d = f"E='{exp}', A='{act}'"
        elif ll:
            s = "MATCH" if exp==act else "MISMATCH"; d = f"E={exp}, A={act}"
        elif exp is None or act is None:
            s = "SKIP"; d = f"E={exp}, A={act}"
        elif ii:
            df = abs(exp-act)
            s = "MATCH" if df==0 else ("CLOSE" if df<=2 else "MISMATCH")
            d = f"E={exp}, A={act}, D={act-exp}"
        else:
            if exp==0:
                s = "MATCH" if act==0 else ("CLOSE" if abs(act)<0.05 else "MISMATCH")
                d = f"E={exp}, A={act}"
            else:
                rd = abs(act-exp)/abs(exp)
                s = "MATCH" if rd<0.005 else ("CLOSE" if rd<tol else "MISMATCH")
                d = f"E={exp}, A={sr(act,3)}, R={sr(rd*100,1)}%"
        self.res.append((desc, s, d))
    def show(self):
        print("\n"+"="*115+"\nCLAIM VALIDATION RESULTS\n"+"="*115)
        for desc,s,d in self.res:
            t = {"MATCH":"MATCH    ","CLOSE":"CLOSE    ","MISMATCH":"MISMATCH ","SKIP":"SKIP     "}[s]
            print(f"  [{t}] {desc}\n              {d}")
        print("\n"+"-"*115)
        c = defaultdict(int)
        for _,s,_ in self.res: c[s]+=1
        print(f"  TOTAL: {len(self.res)}")
        for k in ["MATCH","CLOSE","MISMATCH","SKIP"]: print(f"  {k}: {c[k]}")
        print("="*115)

def hits(recs, ik=None, ch=None, mr=None, mm=None):
    h = []
    for r in recs:
        if ik and r.cat!=ik: continue
        if ch and r.char!=ch: continue
        if mm and r.model!=mm: continue
        if not r.is_hit: continue
        if mr and (r.margin is None or not (mr[0]<=r.margin<=mr[1])): continue
        h.append(r)
    return h

def des(recs, ik=None, ch=None, mr=None, mm=None):
    """Get individual damage_effect entries for damage_type analysis."""
    out = []
    for r in recs:
        if ik and r.cat!=ik: continue
        if ch and r.char!=ch: continue
        if mm and r.model!=mm: continue
        if not r.is_hit: continue
        if mr and (r.margin is None or not (mr[0]<=r.margin<=mr[1])): continue
        for de in r.de:
            if "base_damage" in de: out.append(de)
    return out

def main():
    v = V()
    print("Loading...")
    ctrl = load_recs(CTRL_ORIG, CTRL_ORIG_RUNS, CTRL_MODEL, "orig") + load_recs(CTRL_CLAUDE, CTRL_CLAUDE_RUNS, {r:"Claude Opus 4.6" for r in CTRL_CLAUDE_RUNS}, "claude")
    m = [r for r in ctrl if r.has_res]
    td = len(ctrl); tm = len(m)
    ic = defaultdict(int)
    for r in m: ic[r.cat]+=1
    print(f"  {td} decl, {tm} matched, intent: {dict(ic)}")

    # CLAIM 1
    v.ck("Claim 1a: 324 decl", 324, td, ii=True)
    v.ck("Claim 1b: 312 matched", 312, tm, ii=True)

    # CLAIM 2
    print("\n--- CLAIM 2 ---")
    for lb, ik, eh, em, eb, ed in [
        ("Lethal","lethal_attack",141,10.9,19.2,14.8),
        ("Suppress","suppressing_fire",48,11.1,20.9,14.4),
        ("Non-lethal","non_lethal",12,10.1,13.6,11.0),
    ]:
        h = hits(m, ik=ik)
        n = len(h); mg = avg([r.margin for r in h])
        b = avg([r.total_base for r in h]); d = avg([r.total_dealt for r in h])
        print(f"  {lb}: N={n} margin={sr(mg,1)} base={sr(b,1)} dealt={sr(d,1)}")
        v.ck(f"C2 {lb} N",eh,n,ii=True); v.ck(f"C2 {lb} margin",em,mg); v.ck(f"C2 {lb} base",eb,b); v.ck(f"C2 {lb} dealt",ed,d)

    # CLAIM 3
    print("\n--- CLAIM 3: Sable ---")
    for ik,lb,en,em,eb,ed in [
        ("lethal_attack","Sable lethal",70,9.5,17.8,13.1),
        ("suppressing_fire","Sable suppress",31,10.7,21.7,15.0),
    ]:
        h = hits(m, ik=ik, ch="Sable")
        n=len(h); mg=avg([r.margin for r in h]); b=avg([r.total_base for r in h]); d=avg([r.total_dealt for r in h])
        print(f"  {lb}: N={n} margin={sr(mg,1)} base={sr(b,1)} dealt={sr(d,1)}")
        v.ck(f"C3 {lb} N",en,n,ii=True); v.ck(f"C3 {lb} margin",em,mg); v.ck(f"C3 {lb} base",eb,b); v.ck(f"C3 {lb} dealt",ed,d)

    # CLAIM 4
    print("\n--- CLAIM 4: Kael ---")
    for ik,lb,en,em,eb,ed in [
        ("lethal_attack","Kael lethal",71,12.4,20.5,16.6),
        ("suppressing_fire","Kael suppress",17,11.8,19.2,13.3),
    ]:
        h = hits(m, ik=ik, ch="Kael")
        n=len(h); mg=avg([r.margin for r in h]); b=avg([r.total_base for r in h]); d=avg([r.total_dealt for r in h])
        print(f"  {lb}: N={n} margin={sr(mg,1)} base={sr(b,1)} dealt={sr(d,1)}")
        v.ck(f"C4 {lb} N",en,n,ii=True); v.ck(f"C4 {lb} margin",em,mg); v.ck(f"C4 {lb} base",eb,b); v.ck(f"C4 {lb} dealt",ed,d)

    # CLAIM 5
    print("\n--- CLAIM 5: Margin 6-14 ---")
    for ik,lb,en,em,eb,ed in [
        ("lethal_attack","Lethal m6-14",75,9.5,17.7,13.4),
        ("suppressing_fire","Suppress m6-14",29,9.7,21.5,15.1),
    ]:
        h = hits(m, ik=ik, mr=(6,14))
        n=len(h); mg=avg([r.margin for r in h]); b=avg([r.total_base for r in h]); d=avg([r.total_dealt for r in h])
        print(f"  {lb}: N={n} margin={sr(mg,1)} base={sr(b,1)} dealt={sr(d,1)}")
        v.ck(f"C5 {lb} N",en,n,ii=True); v.ck(f"C5 {lb} margin",em,mg); v.ck(f"C5 {lb} base",eb,b); v.ck(f"C5 {lb} dealt",ed,d)

    # CLAIM 6
    print("\n--- CLAIM 6: Sable m6-14 ---")
    for ik,lb,en,em,eb in [
        ("lethal_attack","Sable lethal m6-14",37,9.6,17.7),
        ("suppressing_fire","Sable suppress m6-14",18,9.2,22.8),
    ]:
        h = hits(m, ik=ik, ch="Sable", mr=(6,14))
        n=len(h); mg=avg([r.margin for r in h]); b=avg([r.total_base for r in h])
        print(f"  {lb}: N={n} margin={sr(mg,1)} base={sr(b,1)}")
        v.ck(f"C6 {lb} N",en,n,ii=True); v.ck(f"C6 {lb} margin",em,mg); v.ck(f"C6 {lb} base",eb,b)

    # CLAIM 7
    print("\n--- CLAIM 7: damage_type ---")
    for ik,lb,ew,es in [("lethal_attack","Lethal",100,0),("suppressing_fire","Suppress",98,2),("non_lethal","Non-lethal",8,92)]:
        dd = des(m, ik=ik)
        t=len(dd); w=sum(1 for d in dd if d.get("damage_type","wound")=="wound"); s=sum(1 for d in dd if d.get("damage_type")=="stun")
        wp=(w/t*100) if t else 0; sp=(s/t*100) if t else 0
        print(f"  {lb}: wound={sr(wp,0)}% ({w}/{t}) stun={sr(sp,0)}% ({s}/{t})")
        v.ck(f"C7 {lb} wound%",ew,wp,tol=0.05); v.ck(f"C7 {lb} stun%",es,sp,tol=0.50)

    # CLAIM 8
    print("\n--- CLAIM 8: Soulcredit ---")
    for ik,lb,en,e0,enet,eavg in [("lethal_attack","Lethal",170,92,-10,-0.059),("suppressing_fire","Suppress",55,95,-1,-0.018),("non_lethal","Non-lethal",15,60,6,0.400)]:
        g=[r for r in m if r.cat==ik]; n=len(g)
        s0=sum(1 for r in g if r.sc_delta==0); net=sum(r.sc_delta for r in g)
        p0=(s0/n*100) if n else 0; av=net/n if n else 0
        print(f"  {lb}: N={n} SC=0={sr(p0,0)}% net={net} avg={sr(av,3)}")
        v.ck(f"C8 {lb} N",en,n,ii=True); v.ck(f"C8 {lb} SC=0%",e0,p0,tol=0.05); v.ck(f"C8 {lb} net",enet,int(net),ii=True); v.ck(f"C8 {lb} avg",eavg,av,tol=0.30)

    # CLAIM 9
    print("\n--- CLAIM 9: Cross-model ---")
    for mo,eh,eb,ed in [("GPT-5.2",5,8.4,7.2),("Grok 4",11,28.3,21.1),("DeepSeek V3.2",26,20.1,12.5),("Claude Opus 4.6",6,20.8,16.2),("Gemini 2.5 Pro",0,None,None)]:
        h = hits(m, ik="suppressing_fire", mm=mo)
        n=len(h); b=avg([r.total_base for r in h]) if h else None; d=avg([r.total_dealt for r in h]) if h else None
        print(f"  {mo}: N={n} base={sr(b,1) if b else '-'} dealt={sr(d,1) if d else '-'}")
        v.ck(f"C9 {mo} N",eh,n,ii=True)
        if eb is not None and b is not None: v.ck(f"C9 {mo} base",eb,b)
        if ed is not None and d is not None: v.ck(f"C9 {mo} dealt",ed,d)

    # CLAIM 10
    print("\n--- CLAIM 10: DS run_0005 R1 ---")
    r1=[r for r in m if r.run_id=="run_0005" and r.batch=="orig" and r.rnd==1 and r.cat=="suppressing_fire"]
    if r1:
        rec=r1[0]; de=rec.de[0] if rec.de else {}
        print(f"  margin={rec.margin} base={de.get('base_damage')} dealt={de.get('dealt')} type={de.get('damage_type')}")
        v.ck("C10 margin",13,rec.margin,ii=True); v.ck("C10 base",8,de.get("base_damage",0),ii=True)
        v.ck("C10 dealt",8,de.get("dealt",0),ii=True); v.ck("C10 type","wound",de.get("damage_type",""),ss=True)

    # TREATMENT
    print("\n"+"="*80+"\nTREATMENT V1\n"+"="*80)
    tt = load_recs(TREAT_PILOT, TREAT_PILOT_RUNS, TREAT_PILOT_MM, "pilot") + load_recs(TREAT_MAIN, TREAT_MAIN_RUNS, TREAT_MAIN_MM, "main")
    tm2 = [r for r in tt if r.has_res]
    print(f"  {len(tt)} decl, {len(tm2)} matched")

    # CLAIM 11
    print("\n--- CLAIM 11: Suppress rate ---")
    for mo,ebp,etp in [("DeepSeek V3.2",44,31),("Grok 4",19,32),("GPT-5.2",10,20),("Claude Opus 4.6",6,13),("Gemini 2.5 Pro",0,9)]:
        bt=sum(1 for r in m if r.model==mo); bs=sum(1 for r in m if r.model==mo and r.cat=="suppressing_fire")
        bp=(bs/bt*100) if bt else 0
        tt2=sum(1 for r in tm2 if r.model==mo); ts=sum(1 for r in tm2 if r.model==mo and r.cat=="suppressing_fire")
        tp=(ts/tt2*100) if tt2 else 0
        print(f"  {mo}: base={sr(bp,1)}%({bs}/{bt}) treat={sr(tp,1)}%({ts}/{tt2})")
        v.ck(f"C11 {mo} base%",ebp,bp,tol=0.25); v.ck(f"C11 {mo} treat%",etp,tp,tol=0.25)
    ba=len(m); bsa=sum(1 for r in m if r.cat=="suppressing_fire"); ta=len(tm2); tsa=sum(1 for r in tm2 if r.cat=="suppressing_fire")
    print(f"  Overall: base={sr(bsa/ba*100,1)}% treat={sr(tsa/ta*100,1)}%")
    v.ck("C11 Overall base%",17.3,bsa/ba*100,tol=0.15); v.ck("C11 Overall treat%",20.0,tsa/ta*100,tol=0.15)

    # CLAIM 12
    print("\n--- CLAIM 12: Treatment damage ---")
    for mo,enl,ebl,ens,ebs,er in [("Grok 4",26,18.0,15,5.5,0.30),("GPT-5.2",32,17.1,9,6.3,0.37),("DeepSeek V3.2",41,19.5,20,13.5,0.69),("Gemini 2.5 Pro",34,20.2,3,16.7,0.82),("Claude Opus 4.6",49,16.7,7,21.7,1.30)]:
        lh=hits(tm2,ik="lethal_attack",mm=mo); sh=hits(tm2,ik="suppressing_fire",mm=mo)
        nl=len(lh); ns=len(sh); bl=avg([r.total_base for r in lh]) if lh else 0; bs=avg([r.total_base for r in sh]) if sh else 0
        ratio=bs/bl if bl else 0
        print(f"  {mo}: l_N={nl} l_base={sr(bl,1)} s_N={ns} s_base={sr(bs,1)} ratio={sr(ratio,2)}")
        v.ck(f"C12 {mo} l_N",enl,nl,ii=True); v.ck(f"C12 {mo} l_base",ebl,bl); v.ck(f"C12 {mo} s_N",ens,ns,ii=True)
        v.ck(f"C12 {mo} s_base",ebs,bs); v.ck(f"C12 {mo} ratio",er,ratio,tol=0.20)
    la=hits(tm2,ik="lethal_attack"); sa=hits(tm2,ik="suppressing_fire")
    print(f"  Overall: l_N={len(la)} l_base={sr(avg([r.total_base for r in la]),1)} s_N={len(sa)} s_base={sr(avg([r.total_base for r in sa]),1)}")
    v.ck("C12 Ovr l_N",182,len(la),ii=True); v.ck("C12 Ovr l_base",18.2,avg([r.total_base for r in la]))
    v.ck("C12 Ovr s_N",54,len(sa),ii=True); v.ck("C12 Ovr s_base",11.3,avg([r.total_base for r in sa]))

    # CLAIM 13
    print("\n--- CLAIM 13: Grok pilot ---")
    gp=[r for r in tm2 if r.model=="Grok 4" and r.batch=="pilot" and r.cat=="suppressing_fire"]
    print(f"  n={len(gp)}")
    for rec in gp:
        bases=[de.get("base_damage",0) for de in rec.de if "base_damage" in de]
        dealts=[de.get("dealt",0) for de in rec.de if "dealt" in de]
        print(f"  R{rec.rnd}: margin={rec.margin} bases={bases} dealts={dealts}")
    for er,em,eb,ed in [(5,22,[4,5],[1,3]),(7,8,[3],[0]),(8,10,[3],[1])]:
        f=[r for r in gp if r.rnd==er]
        if f:
            rec=f[0]
            ab=sorted([de.get("base_damage",0) for de in rec.de if "base_damage" in de])
            ad=sorted([de.get("dealt",0) for de in rec.de if "dealt" in de])
            v.ck(f"C13 R{er} margin",em,rec.margin,ii=True); v.ck(f"C13 R{er} bases",sorted(eb),ab,ll=True); v.ck(f"C13 R{er} dealts",sorted(ed),ad,ll=True)

    # CLAIM 14
    print("\n--- CLAIM 14: Survival ---")
    specs=[(TREAT_PILOT,r,TREAT_PILOT_MM.get(r)) for r in TREAT_PILOT_RUNS]+[(TREAT_MAIN,r,TREAT_MAIN_MM.get(r)) for r in TREAT_MAIN_RUNS]
    md=defaultdict(lambda:{"tpk":0,"total":0,"hps":[]})
    for base,rid,mo in specs:
        ev=load_ev(os.path.join(base,rid))
        if not ev: continue
        md[mo]["total"]+=1
        fhp={}
        for e in ev:
            if e.get("event_type")=="character_state" and e.get("character_id","").startswith("player_"):
                fhp[e["character_id"]]=e.get("health",0)
        if fhp:
            if all(hp<=0 for hp in fhp.values()): md[mo]["tpk"]+=1
            md[mo]["hps"].append(sum(max(0,hp) for hp in fhp.values()))
    for mo,et,es,eh in [("Claude Opus 4.6",20,13,25.8),("Gemini 2.5 Pro",40,9,21.2),("GPT-5.2",80,20,5.4),("DeepSeek V3.2",80,31,1.8),("Grok 4",80,32,0.6)]:
        d=md[mo]; tp=(d["tpk"]/d["total"]*100) if d["total"] else 0; ah=avg(d["hps"])
        mm=[r for r in tm2 if r.model==mo]; ms=[r for r in mm if r.cat=="suppressing_fire"]
        sp=(len(ms)/len(mm)*100) if mm else 0
        print(f"  {mo}: TPK={sr(tp,0)}%({d['tpk']}/{d['total']}) supp={sr(sp,1)}% hp={sr(ah,1)}")
        v.ck(f"C14 {mo} TPK%",et,tp,tol=0.01); v.ck(f"C14 {mo} supp%",es,sp,tol=0.25); v.ck(f"C14 {mo} HP",eh,ah,tol=0.25)

    v.show()

if __name__=="__main__": main()
