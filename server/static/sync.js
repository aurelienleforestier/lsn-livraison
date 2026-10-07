// Central state synchronization. The test instance rejects conflicting writes
// rather than overwriting work submitted by another terminal.
let serverVersion=0, pendingState=null, saveBusy=false, syncBlocked=false, lastServerSnapshot='';
function cloneJson(x){return JSON.parse(JSON.stringify(x))}
function statusSync(text,bad=false){let e=document.getElementById('syncStatus');if(!e){e=document.createElement('div');e.id='syncStatus';e.style.cssText='padding:8px 16px;font-size:12px;background:#f1f5f9';document.querySelector('nav').after(e)}e.textContent=text;e.style.color=bad?'#991b1b':'#334155'}
function save(){
 saveUi();if(!serverReady||syncBlocked)return;
 const snapshot=serverStateSnapshot(),json=JSON.stringify(snapshot);
 if(json===lastServerSnapshot&&!saveBusy&&!pendingState)return;
 pendingState=snapshot;statusSync('Enregistrement…');clearTimeout(serverSaveTimer);serverSaveTimer=setTimeout(flushState,80);
}
async function flushState(){
 if(saveBusy||!pendingState||syncBlocked)return;
 saveBusy=true;const snapshot=pendingState;pendingState=null;
 try{
  const r=await apiJson('/api/state',{method:'PUT',body:JSON.stringify({state:snapshot,version:serverVersion})});
  serverVersion=r.version;lastServerSnapshot=JSON.stringify(snapshot);
  if(r.state?.tourRunMeta)for(const [rid,meta] of Object.entries(r.state.tourRunMeta)){
   if(meta.operator){state.tourRunMeta[rid]=state.tourRunMeta[rid]||{};state.tourRunMeta[rid].operator=meta.operator;
    if(pendingState){pendingState.tourRunMeta=pendingState.tourRunMeta||{};pendingState.tourRunMeta[rid]=pendingState.tourRunMeta[rid]||{};pendingState.tourRunMeta[rid].operator=meta.operator}}
  }
  if(!pendingState){if(!isPharmacist()){state.tourHistory=[];state.binAdjustments=[];}lastServerSnapshot=JSON.stringify(serverStateSnapshot());statusSync('Données enregistrées sur le serveur');}
 }catch(e){
  syncBlocked=true;statusSync('Action NON enregistrée : '+e.message+' Recharge la page avant de continuer.',true);
  const box=n('bootNotice');box.style.display='block';box.textContent='Cette action n’a pas été enregistrée. '+e.message+' ';
  const button=document.createElement('button');button.className='mini';button.textContent='RECHARGER LES DONNÉES';button.onclick=()=>{syncBlocked=false;location.reload()};box.append(button);
 }finally{saveBusy=false;if(pendingState&&!syncBlocked)flushState()}
}
function ownedRoute(rid){const owner=state.tourRunMeta?.[rid]?.operator?.id;return !owner||String(owner)===String(state.currentUser.id)}
function activeDeliveryRouteId(){return Object.keys(state.deliveryStarted||{}).find(rid=>state.deliveryStarted[rid]&&ownedRoute(rid))||null}
function activeWorkflowRouteId(){return activeDeliveryRouteId()||Object.keys(state.loadByRoute||{}).find(rid=>ownedRoute(rid)&&routeHasPhysicalLoad(rid))||null}
const selectBase=selectRoute;
selectRoute=function(id){if(state.busyRoutes?.[id]||(!ownedRoute(id)&&(routeHasPhysicalLoad(id)||state.deliveryStarted[id]))){alert('Cette tournée est utilisée par un autre opérateur.');return}selectBase(id)};
const baseRenderDriver=renderDriverRoutes;
renderDriverRoutes=function(){baseRenderDriver();for(const r of state.routes){if(state.busyRoutes?.[r.id]||(!ownedRoute(r.id)&&(routeHasPhysicalLoad(r.id)||state.deliveryStarted[r.id]))){const button=n('driverRoutes').querySelector(`button[onclick="selectRoute('${r.id}')"]`);if(button){button.disabled=true;button.textContent='DÉJÀ EN COURS — AUTRE OPÉRATEUR'}}}};
const baseRenderAdmin=renderAdmin;
renderAdmin=function(){if(!isPharmacist()){n('adminRoutes').replaceChildren();n('adminDetail').replaceChildren();return}baseRenderAdmin()};
async function bootServerApp(){
 try{
  const me=await apiJson('/api/me',{method:'GET'});csrfToken=me.csrf||'';if(me.user.mustChangePassword){location.replace('/change-password');return}
  const payload=await apiJson('/api/state',{method:'GET'});serverVersion=payload.version;state=normalizeServerState(payload.state);state.currentUser=me.user;
  try{const ui=JSON.parse(localStorage.getItem(uiStorageKey())||'{}');state.selectedRoute=state.routes.some(r=>r.id===ui.selectedRoute)?ui.selectedRoute:null;state.adminSelectedRoute=isPharmacist()?ui.adminSelectedRoute:null;state.currentScreen=['home','load','delivery','park','history','kpi','profiles','admin'].includes(ui.currentScreen)?ui.currentScreen:'home'}catch(e){}
  const rid=activeWorkflowRouteId();if(rid){state.selectedRoute=rid;if(state.deliveryStarted[rid])state.currentScreen='delivery'}
  lastServerSnapshot=JSON.stringify(serverStateSnapshot());serverReady=true;renderAccess();go(state.currentScreen||'home');statusSync('Version de test · données fictives uniquement');
  setInterval(refreshRemoteState,6000);
 }catch(e){showBootError(e)}
}
async function refreshRemoteState(){
 if(!serverReady||pendingState||saveBusy||syncBlocked||document.hidden)return;
 if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)||currentLoadPharmacy||n('camera')?.classList.contains('open'))return;
 try{
  const payload=await apiJson('/api/state',{method:'GET'});if(payload.version===serverVersion)return;
  const ui={currentUser:state.currentUser,selectedRoute:state.selectedRoute,adminSelectedRoute:state.adminSelectedRoute,currentScreen:state.currentScreen};
  state={...normalizeServerState(payload.state),...ui};serverVersion=payload.version;lastServerSnapshot=JSON.stringify(serverStateSnapshot());render();statusSync('Données mises à jour depuis le serveur');
 }catch(e){statusSync('Connexion au serveur indisponible. Réessaie avant de poursuivre.',true)}
}
async function logoutApp(){
 clearTimeout(serverSaveTimer);await flushState();if(saveBusy||pendingState||syncBlocked){alert('Attends la confirmation de l’enregistrement avant la déconnexion.');return}
 await apiJson('/api/auth/logout',{method:'POST',body:'{}'});location.replace('/login');
}
window.addEventListener('beforeunload',event=>{if(saveBusy||pendingState||syncBlocked){event.preventDefault();event.returnValue='Une action n’est pas encore enregistrée.'}});

const baseStartDelivery=startDeliveryTour;
startDeliveryTour=function(){const r=routeObj();if(r){const m=state.tourRunMeta[r.id];if(m&&!m.startedAt){m.startedAt=Date.now();m.runId='RUN-'+m.startedAt+'-'+r.id;}}baseStartDelivery();};
