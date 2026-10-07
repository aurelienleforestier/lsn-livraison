def apply_controls(html):
    def replace(old,new):
        nonlocal html
        if html.count(old)!=1: raise RuntimeError('Point de correction introuvable : '+old[:80])
        html=html.replace(old,new)
    replace("parcelOverrideConfirmed:!!d.parcelOverrideConfirmed}","parcelOverrideConfirmed:!!d.parcelOverrideConfirmed,correctionReason:d.correctionReason||'',discrepancyReason:d.discrepancyReason||''}")
    replace("state.bins.available=[...new Set(state.bins.available.concat(validReturns))];d.done=true;", "state.bins.returning=state.bins.returning||{};for(const code of validReturns)state.bins.returning[code]={routeId:r.id,pharmacyId:pid};d.done=true;")
    replace("const confirmationDiffs=[];", "const confirmationDiffs=[];")
    replace(" state.bins.client[pid]=held.filter", " if(confirmationDiffs.length){const reason=prompt('Motif de l’écart (au moins 5 caractères) :');if(!reason||reason.trim().length<5)return;d.discrepancyReason=reason.trim();}\n state.bins.client[pid]=held.filter")
    replace("if(!d.done)return;\n const validReturns=", "if(!d.done)return;const reason=prompt('Motif de la correction (au moins 5 caractères) :');if(!reason||reason.trim().length<5)return;d.correctionReason=reason.trim();\n const validReturns=")
    replace("state.bins.client[pid]=before;state.bins.available=", "state.bins.returning=state.bins.returning||{};for(const code of validReturns)delete state.bins.returning[code];state.bins.client[pid]=before;state.bins.available=")
    replace(" const meta=state.tourRunMeta[r.id]||{};const endedAt=", " if(!confirm('Confirmer la réception PHYSIQUE au dépôt de tous les bacs de retour et non livrés avant de clôturer ?'))return;\n state.bins.returning=state.bins.returning||{};for(const [pid,l] of Object.entries(loads)){const d=delivered[pid]||{};for(const code of l.bins||[])if(!(d.bins||[]).includes(code)&&!state.bins.available.includes(code))state.bins.available.push(code);}\n for(const [code,info] of Object.entries(state.bins.returning))if(info.routeId===r.id){if(!state.bins.available.includes(code))state.bins.available.push(code);delete state.bins.returning[code];}\n const meta=state.tourRunMeta[r.id]||{};const endedAt=")
    html=html.replace("pharmacyId:pid,pharmacyName:ph(pid)?.name||pid,loadedBins:l.bins.length", "discrepancyReason:d.discrepancyReason||\'\',correctionReason:d.correctionReason||\'\',pharmacyId:pid,pharmacyName:ph(pid)?.name||pid,loadedBins:l.bins.length")
    replace("state.tourHistory.push({id:meta.runId", "state.tourHistory.push({depotReceiptConfirmed:true,id:meta.runId")
    replace("✓ TERMINER LA TOURNÉE", "✓ CONFIRMER LE RETOUR DÉPÔT ET TERMINER")
    replace("if(!d?.noOrder&&!delivered?.[pid]?.done)(d?.bins||[]).forEach(b=>activeLoaded.add(b));", "if(!d?.noOrder)(d?.bins||[]).filter(b=>!delivered?.[pid]?.done||!(delivered[pid].bins||[]).includes(b)).forEach(b=>activeLoaded.add(b));")
    replace("n('loadedCount').textContent=activeLoaded.size;", "n('loadedCount').textContent=activeLoaded.size+Object.keys(state.bins.returning||{}).length;")
    replace(" const pname=ph(holder.pid)?.name||holder.pid;", " const reason=prompt('Motif de la restitution au dépôt (au moins 5 caractères) :');if(!reason||reason.trim().length<5)return;\n const pname=ph(holder.pid)?.name||holder.pid;")
    replace("state.binAdjustments.push({bin:code,", "state.binAdjustments.push({reason:reason.trim(),bin:code,")
    replace("if(!code||d.done)return;stampFirstAction(d);if(!load.bins.includes(code))", "if(!code||d.done)return;stampFirstAction(d);if(!load.bins.includes(code))")
    replace("function handleBinLoad(){", "function handleBinLoad(){")
    # normalizeServerState copies only known bins fields; retain return custody explicitly.
    html=html.replace("const out=freshState();", "const out=freshState();")
    # Add return map to normalized output immediately before returning it.
    marker="function normalizeServerState("
    start=html.index(marker);end=html.index('\n}',start)
    part=html[start:end]
    if 'return out' not in part: raise RuntimeError('Normalisation serveur non reconnue')
    part=part.replace('return out',"out.bins.returning=x.bins?.returning||{};return out")
    html=html[:start]+part+html[end:]
    return html
