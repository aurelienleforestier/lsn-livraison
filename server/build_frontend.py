"""Rebuild the authenticated client from the checked, unchanged prototype.
No network requests and no modification to index.html or the main branch.
"""
from pathlib import Path
import hashlib
import re

ROOT = Path(__file__).resolve().parent.parent
SOURCE_BLOB = "3a6733e22a4dcdb318a04b9e98310b8dae599671"
TARGET_SHA256 = "e6b6b1dcce53b0070d9aec3ec373be3666c110e3f511afa717408c92130db9ab"


def main():
    source = (ROOT / "index.html").read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()
    if blob != SOURCE_BLOB:
        raise RuntimeError("La page source a changé. Vérifier la version avant publication.")
    lines = source.decode("utf-8").splitlines(keepends=True)
    patch = (ROOT / "server/frontend.patch").read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    cursor = 0
    i = 2
    while i < len(patch):
        match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n?", patch[i])
        if not match:
            raise RuntimeError(f"Entête de modification invalide à la ligne {i + 1}")
        old_start = int(match[1])
        old_count = int(match[2]) if match[2] is not None else 1
        new_count = int(match[4]) if match[4] is not None else 1
        start = old_start if old_count == 0 else old_start - 1
        if start < cursor:
            raise RuntimeError("Modifications superposées")
        out.extend(lines[cursor:start])
        cursor = start
        consumed = added = 0
        i += 1
        while i < len(patch) and not patch[i].startswith("@@ "):
            kind, value = patch[i][0], patch[i][1:]
            if kind in ("-", " "):
                if cursor >= len(lines) or lines[cursor] != value:
                    raise RuntimeError(f"Source différente à la ligne {cursor + 1}")
                cursor += 1
                consumed += 1
            if kind in ("+", " "):
                out.append(value)
                added += 1
            if kind not in ("-", "+", " "):
                raise RuntimeError("Modification non prise en charge")
            i += 1
        if consumed != old_count or added != new_count:
            raise RuntimeError("Nombre de lignes incohérent")
    out.extend(lines[cursor:])
    result = "".join(out).encode("utf-8")
    if hashlib.sha256(result).hexdigest() != TARGET_SHA256:
        raise RuntimeError("Le résultat ne correspond pas à la version vérifiée")

    # Correctifs spécifiques à la version serveur de test.
    html = result.decode("utf-8")

    old_release = '<input id="releaseBinCode" class="input" placeholder="Ex. BAC-000007" autocomplete="off">'
    new_release = '<input id="releaseBinCode" name="lsn_bin_release_code" class="input" type="search" placeholder="Ex. BAC-000007" autocomplete="new-password" autocapitalize="characters" spellcheck="false" data-lpignore="true">'
    if html.count(old_release) != 1:
        raise RuntimeError("Champ de restitution introuvable ou ambigu")
    html = html.replace(old_release, new_release)

    old_park = '''function renderPark(){
 const activeLoaded=new Set(),rid=activeWorkflowRouteId();if(rid){const loads=state.loadByRoute?.[rid]||{},delivered=state.deliveredByRoute?.[rid]||{};Object.entries(loads).forEach(([pid,d])=>{if(!d?.noOrder&&!delivered?.[pid]?.done)(d?.bins||[]).forEach(b=>activeLoaded.add(b))})}
 const client=Object.values(state.bins.client).reduce((a,x)=>a+(Array.isArray(x)?x.length:0),0);n('availableCount').textContent=state.bins.available.length;n('loadedCount').textContent=activeLoaded.size;n('clientCount').textContent=client;n('parkDetails').innerHTML=Object.entries(state.bins.client).filter(([,b])=>Array.isArray(b)&&b.length).map(([pid,b])=>`<div class="card"><strong>${ph(pid)?.name||pid}</strong><div class="meta">${b.length} bac(s) : ${b.join(', ')||'aucun'}</div></div>`).join('')||'<div class="small">Aucun bac actuellement enregistré chez un client.</div>';
}'''
    new_park = '''function renderPark(){
 const activeLoaded=new Set();
 for(const [rid,loads] of Object.entries(state.loadByRoute||{})){
   const delivered=state.deliveredByRoute?.[rid]||{};
   Object.entries(loads||{}).forEach(([pid,d])=>{
     if(!d?.noOrder&&!delivered?.[pid]?.done)(d?.bins||[]).forEach(b=>activeLoaded.add(b));
   });
 }
 const client=Object.values(state.bins.client).reduce((a,x)=>a+(Array.isArray(x)?x.length:0),0);n('availableCount').textContent=state.bins.available.length;n('loadedCount').textContent=activeLoaded.size;n('clientCount').textContent=client;n('parkDetails').innerHTML=Object.entries(state.bins.client).filter(([,b])=>Array.isArray(b)&&b.length).map(([pid,b])=>`<div class="card"><strong>${ph(pid)?.name||pid}</strong><div class="meta">${b.length} bac(s) : ${b.join(', ')||'aucun'}</div></div>`).join('')||'<div class="small">Aucun bac actuellement enregistré chez un client.</div>';
}'''
    if html.count(old_park) != 1:
        raise RuntimeError("Fonction renderPark introuvable ou ambiguë")
    html = html.replace(old_park, new_park)
    result = html.encode("utf-8")

    target = ROOT / "server/static/app.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(result)
    print("LSN PHARMA : interface de test reconstruite et vérifiée.")


if __name__ == "__main__":
    main()
