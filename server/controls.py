"""Server-side custody controls; never trust browser inventory assertions."""
import re
from fastapi import HTTPException

def reject(message, code=400):
    raise HTTPException(code, message)

def locations(s):
    result={}
    def add(code, where):
        if not isinstance(code,str) or not re.fullmatch(r'BAC-[A-Z0-9-]{1,40}',code): reject('Numéro de bac invalide')
        if code in result: reject('Double affectation de '+code,409)
        result[code]=where
    bins=s.get('bins',{})
    if not isinstance(bins,dict) or not isinstance(bins.get('available'),list) or not isinstance(bins.get('client'),dict) or not isinstance(bins.get('returning',{}),dict): reject('Parc invalide')
    for code in bins['available']: add(code,('warehouse',))
    for pid,codes in bins['client'].items():
        if not re.fullmatch(r'PH-[0-9]+',pid) or not isinstance(codes,list): reject('Affectation client invalide')
        for code in codes: add(code,('client',pid))
    for code,info in bins.get('returning',{}).items():
        if not isinstance(info,dict) or not isinstance(info.get('routeId'),str): reject('Retour invalide')
        add(code,('returning',info['routeId']))
    routes=s.get('routes')
    if not isinstance(routes,list) or len(routes)>300 or any(not isinstance(r,dict) for r in routes): reject('Tournées invalides')
    if any(not isinstance(r.get('id'),str) or not isinstance(r.get('pharmacies',[]),list) or any(not isinstance(x,str) for x in r.get('pharmacies',[])) for r in routes): reject('Structure tournée invalide')
    membership={r.get('id'):r.get('pharmacies',[]) for r in routes}
    for key in ('loadByRoute','deliveredByRoute','tourRunMeta','deliveryStarted','deliveryCursorByRoute'):
        if not isinstance(s.get(key,{}),dict): reject('État de tournée invalide')
    for key in ('loadByRoute','deliveredByRoute'):
        for rid,items in s.get(key,{}).items():
            if rid not in membership or not isinstance(items,dict): reject('Tournée inconnue')
            for pid,d in items.items():
                if pid not in membership[rid] or not isinstance(d,dict): reject('Pharmacie hors tournée')
                for field in ('bins','returns','manualBins','wrongReturns'):
                    if field in d and (not isinstance(d[field],list) or any(not isinstance(x,str) for x in d[field]) or len(set(d[field]))!=len(d[field])): reject('Liste de bacs invalide')
                if type(d.get('parcels',0)) is not int or not 0<=d.get('parcels',0)<=10000: reject('Nombre de colis invalide')
                if key=='deliveredByRoute' and not set(d.get('bins',[]))<=set(s.get('loadByRoute',{}).get(rid,{}).get(pid,{}).get('bins',[])): reject('Bac livré non chargé')
    for rid,items in s.get('loadByRoute',{}).items():
        for pid,l in items.items():
            d=s.get('deliveredByRoute',{}).get(rid,{}).get(pid,{})
            for code in l.get('bins',[]):
                if not (d.get('done') and code in d.get('bins',[])): add(code,('vehicle',rid,pid))
    return result

def control_transition(old,new,operator):
    before=locations(old); after=locations(new)
    history=old.get('tourHistory',[]); incoming=new.get('tourHistory',[])
    if not isinstance(incoming,list) or incoming[:len(history)]!=history: reject('Historique archivé non modifiable',403)
    additions=incoming[len(history):]
    closed=set()
    for h in additions:
        if not isinstance(h,dict) or not h.get('depotReceiptConfirmed'): reject('Confirmation physique du retour dépôt requise')
        rid=h.get('routeId'); loads=old.get('loadByRoute',{}).get(rid,{})
        deliveries=old.get('deliveredByRoute',{}).get(rid,{})
        targets={p for p,l in loads.items() if not l.get('noOrder') and (l.get('bins') or l.get('parcels'))}
        if not targets or any(not deliveries.get(p,{}).get('done') for p in targets): reject('Livraisons incomplètes')
        records={r.get('pharmacyId'):r for r in h.get('records',[]) if isinstance(r,dict)}
        if set(records)!=targets: reject('Archivage incomplet')
        for pid in targets:
            r=records[pid];l=loads[pid];d=deliveries[pid]
            for field,expected in [('loadedBinIds',l.get('bins',[])),('deliveredBinIds',d.get('bins',[])),('returnedBinIds',d.get('returns',[]))]:
                if r.get(field)!=expected: reject('Archivage incohérent')
            if r.get('loadedParcels')!=l.get('parcels',0) or r.get('deliveredParcels')!=d.get('parcels',0): reject('Archivage colis incohérent')
        if new.get('loadByRoute',{}).get(rid) or new.get('deliveredByRoute',{}).get(rid): reject('Clôture incohérente')
        closed.add(rid)
    oldadj=old.get('binAdjustments',[]); adj=new.get('binAdjustments',[])
    if not isinstance(adj,list) or adj[:len(oldadj)]!=oldadj: reject('Historique ajustements non modifiable',403)
    corrections={}
    for x in adj[len(oldadj):]:
        if not isinstance(x,dict) or x.get('type')!='warehouse_return_correction' or not isinstance(x.get('reason'),str) or len(x['reason'].strip())<5: reject('Ajustement documenté requis',403)
        code=x.get('bin');pid=x.get('fromPharmacy')
        if before.get(code)!=('client',pid) or after.get(code)!=('warehouse',): reject('Ajustement physique incohérent',403)
        corrections[code]=x
    if operator and set(before)!=set(after): reject('Création ou disparition de bac interdite',403)
    for rid, items in new.get('deliveredByRoute',{}).items():
        for pid,d in items.items():
            prior=old.get('deliveredByRoute',{}).get(rid,{}).get(pid,{})
            load=new.get('loadByRoute',{}).get(rid,{}).get(pid,{})
            if d.get('done') and not prior.get('done'):
                if (len(d.get('bins',[]))!=len(load.get('bins',[])) or d.get('parcels',0)!=load.get('parcels',0)) and len(d.get('discrepancyReason','').strip())<5: reject('Motif de l’écart requis')
            if prior.get('done') and prior!=d and len(d.get('correctionReason','').strip())<5: reject('Motif de correction requis')
    for rid,items in old.get('loadByRoute',{}).items():
        if old.get('deliveryStarted',{}).get(rid) and rid not in closed and items!=new.get('loadByRoute',{}).get(rid,{}): reject('Chargement figé pendant la livraison')
    moves=[]
    for code in set(before)|set(after):
        b=before.get(code);a=after.get(code)
        if a==b: continue
        allowed=False
        if b and a:
            if b[0]=='warehouse' and a[0]=='vehicle': allowed=not old.get('deliveryStarted',{}).get(a[1])
            elif b[0]=='vehicle':
                rid,pid=b[1:];d=new.get('deliveredByRoute',{}).get(rid,{}).get(pid,{})
                if a==('client',pid): allowed=bool(d.get('done') and code in d.get('bins',[]))
                if a==('warehouse',): allowed=rid in closed or not old.get('deliveryStarted',{}).get(rid) and not old.get('deliveredByRoute',{}).get(rid,{}).get(pid,{}).get('done')
            elif b[0]=='client' and a[0]=='returning':
                d=new.get('deliveredByRoute',{}).get(a[1],{}).get(b[1],{})
                allowed=bool(d.get('done') and code in d.get('returns',[]) and code not in d.get('wrongReturns',[]))
            elif b[0]=='returning' and a==('warehouse',): allowed=b[1] in closed
            if code in corrections: allowed=True
            # A documented reopening restores the exact prior pharmacy custody.
            if a[0]=='vehicle' and b[0]=='client' and a[2]==b[1]:
                d=old.get('deliveredByRoute',{}).get(a[1],{}).get(a[2],{});n=new.get('deliveredByRoute',{}).get(a[1],{}).get(a[2],{})
                allowed=bool(d.get('done') and not n.get('done') and len(n.get('correctionReason','').strip())>=5)
            if b[0]=='returning' and a[0]=='client':
                d=new.get('deliveredByRoute',{}).get(b[1],{}).get(a[1],{})
                allowed=bool(not d.get('done') and len(d.get('correctionReason','').strip())>=5)
        if not allowed and operator: reject('Mouvement de bac non autorisé : '+code,403)
        moves.append({'bin':code,'before':b,'after':a})
    return moves
