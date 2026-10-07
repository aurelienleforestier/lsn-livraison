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


/* Mode Zebra terrain : DataWedge (sortie clavier) alimente un champ invisible.
   Aucun bouton de caméra/scan n'est nécessaire dans le chargement. */
(function installZebraLoadingMode(){
 const style=document.createElement('style');
 style.textContent=`
  #zebraCapture{position:fixed!important;left:-10000px!important;top:0!important;width:1px!important;height:1px!important;opacity:.001!important;pointer-events:none!important}
  #loadScanBox .scangrid,#loadScanBox #pharmacyLoad,#loadScanBox #pharmacyLoad + .btn{display:none!important}
  #activeLoadPharmacy .scangrid{display:none!important}
  #activeLoadPharmacy #binLoad,#activeLoadPharmacy #binLoad + .btn{display:none!important}
  #activeLoadPharmacy.zebra-manual #binLoad,#activeLoadPharmacy.zebra-manual #binLoad + .btn{display:block!important}
  .zebra-ready{padding:11px 12px;border-radius:12px;background:#eef2ff;color:#3730a3;font-size:13px;font-weight:700;margin:8px 0}
 `;
 document.head.appendChild(style);

 const capture=document.createElement('input');
 capture.id='zebraCapture';
 capture.type='text';
 capture.inputMode='none';
 capture.autocomplete='off';
 capture.setAttribute('aria-hidden','true');
 document.body.appendChild(capture);

 let scanTimer=null;
 function loadingScanContext(){
   return state?.currentScreen==='load' && !!state?.selectedRoute;
 }
 function focusCapture(){
   if(!loadingScanContext())return;
   const ae=document.activeElement;
   if(ae && (ae.id==='binLoad' || ae.closest?.('#manualBinLoadControls')))return;
   try{capture.focus({preventScroll:true});capture.select()}catch(e){try{capture.focus()}catch(_){}}
 }
 function processCapture(){
   const value=String(capture.value||'').trim();
   capture.value='';
   if(!value||!loadingScanContext())return;
   if(currentLoadPharmacy){
     const input=n('binLoad');
     if(!input)return;
     input.value=value;
     handleBinLoad();
   }else{
     const input=n('pharmacyLoad');
     if(!input)return;
     input.value=value;
     handlePharmacyLoad();
   }
   setTimeout(focusCapture,80);
 }
 capture.addEventListener('keydown',e=>{
   if(e.key==='Enter'||e.key==='Tab'){
     e.preventDefault();
     clearTimeout(scanTimer);
     processCapture();
   }
 });
 capture.addEventListener('input',()=>{
   clearTimeout(scanTimer);
   scanTimer=setTimeout(processCapture,140);
 });

 function decorateLoadUi(){
   const scanBox=n('loadScanBox');
   if(scanBox){
     const h=scanBox.querySelector('h3');
     const s=scanBox.querySelector('.small');
     if(h)h.textContent='Scanner le QR code de la pharmacie';
     if(s)s.textContent='Appuie sur la gâchette du Zebra. La pharmacie s’ouvre automatiquement après lecture.';
   }
   const wrap=n('activeLoadPharmacy');
   if(wrap && currentLoadPharmacy){
     const label=wrap.querySelector('.label');
     if(label && !wrap.querySelector('.zebra-ready')){
       const hint=document.createElement('div');
       hint.className='zebra-ready';
       hint.textContent='Zebra prêt : appuie sur la gâchette pour scanner les bacs.';
       label.insertAdjacentElement('afterend',hint);
     }
     if(!wrap.querySelector('#manualBinLoadToggle')){
       const input=n('binLoad');
       const add=input?.nextElementSibling;
       if(input && add){
         const controls=document.createElement('div');
         controls.id='manualBinLoadControls';
         controls.style.marginTop='6px';
         const toggle=document.createElement('button');
         toggle.id='manualBinLoadToggle';
         toggle.className='mini';
         toggle.textContent='SAISIE MANUELLE';
         toggle.onclick=()=>{
           wrap.classList.toggle('zebra-manual');
           const open=wrap.classList.contains('zebra-manual');
           toggle.textContent=open?'MASQUER LA SAISIE MANUELLE':'SAISIE MANUELLE';
           if(open){input.style.display='block';add.style.display='block';input.focus();}
           else{input.blur();setTimeout(focusCapture,30);}
         };
         controls.appendChild(toggle);
         add.insertAdjacentElement('afterend',controls);
       }
     }
   }
   setTimeout(focusCapture,60);
 }

 const _renderLoad=renderLoad;
 renderLoad=function(){const x=_renderLoad.apply(this,arguments);decorateLoadUi();return x};
 const _renderActiveLoad=renderActiveLoad;
 renderActiveLoad=function(){const x=_renderActiveLoad.apply(this,arguments);decorateLoadUi();return x};
 const _go=go;
 go=function(id){const x=_go.apply(this,arguments);setTimeout(focusCapture,80);return x};

 document.addEventListener('pointerup',e=>{
   if(!loadingScanContext())return;
   if(e.target.closest?.('input,textarea,select'))return;
   setTimeout(focusCapture,120);
 });
 window.addEventListener('focus',()=>setTimeout(focusCapture,100));
 setTimeout(decorateLoadUi,100);
})();
