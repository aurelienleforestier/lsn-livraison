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
  #loadScanBox .small{display:none!important}
  #loadScanBox h3{margin:0!important;text-align:center!important;font-size:20px!important;line-height:1.25!important}
  #loadScanBox{padding:24px 16px!important}
  #activeLoadPharmacy .scangrid{display:none!important}
  #activeLoadPharmacy #binLoad,#activeLoadPharmacy #binLoad + .btn{display:none!important}
  #activeLoadPharmacy.zebra-manual #binLoad,#activeLoadPharmacy.zebra-manual #binLoad + .btn{display:block!important}
  #activeLoadPharmacy .zebra-bin-panel{border:2px dashed #93c5fd;background:#eff6ff;border-radius:18px;padding:24px 16px;margin:14px 0;text-align:center;font-size:20px;font-weight:800;line-height:1.25}
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
     if(s)s.textContent='';
   }
   const wrap=n('activeLoadPharmacy');
   if(wrap && currentLoadPharmacy){
     const label=wrap.querySelector('.label');
     if(label && !wrap.querySelector('.zebra-bin-panel')){
       label.style.display='none';
       const panel=document.createElement('div');
       panel.className='zebra-bin-panel';
       panel.textContent='Scanner les bacs';
       label.insertAdjacentElement('afterend',panel);
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


/* Identité visuelle LSN PHARMA + ergonomie des profils + sécurité d'inactivité. */
(function installLsnBrandAndSecurity(){
 const style=document.createElement('style');
 style.textContent=`
  :root{--blue:#2d357f!important;--text:#202750!important;--green:#008875!important;--line:#dfe2e9!important;--bg:#f7f8f4!important;--pink:#df0084!important}
  body{background:#f7f8f4!important;color:#202750!important}
  .app{background:#fff!important}
  header{border-bottom-color:#dfe2e9!important}
  header .logo{display:flex;align-items:center;min-width:120px}
  header .logo img{display:block;width:122px;height:auto;max-height:62px;object-fit:contain}
  #userRoleBadge{display:none!important}
  #userNameBadge{background:#eef0fb!important;color:#2d357f!important;font-weight:800!important}
  nav button.active,.btn.dark{background:#2d357f!important;color:#fff!important}
  .btn.primary{background:#2d357f!important;color:#fff!important}
  .btn.green{background:#008875!important;color:#fff!important}
  .status.ok,.notice.ok{background:#e2f4ef!important;color:#006b5d!important}
  .scanbox,#activeLoadPharmacy .zebra-bin-panel{border-color:#98a4d8!important;background:#f3f5ff!important;color:#202750!important}
  a{color:#008875}
  body.operator-mode nav{justify-content:center!important;overflow-x:hidden!important}
  body.operator-mode nav button{flex:0 0 auto}
  @media(max-width:520px){
    header{padding:10px 12px!important;gap:10px}
    header .logo img{width:102px}
    #userNameBadge{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    body.operator-mode nav{gap:7px!important;padding:9px 6px!important}
    body.operator-mode nav button{font-size:12px!important;padding:8px 9px!important}
  }
 `;
 document.head.appendChild(style);

 function decorateBrand(){
   const logo=document.querySelector('header .logo');
   if(logo && !logo.querySelector('img')){
     logo.innerHTML='<img src="/lsn-logo.svg" alt="LSN PHARMA">';
   }
   const role=n('userRoleBadge');if(role)role.style.display='none';
   const name=n('userNameBadge');if(name)name.textContent=state?.currentUser?.name||state?.currentUser?.email||'Utilisateur';
   document.body.classList.toggle('operator-mode',!isPharmacist());
 }
 const _renderAccessBrand=renderAccess;
 renderAccess=function(){const x=_renderAccessBrand.apply(this,arguments);decorateBrand();return x};

 const _renderProfilesBrand=renderProfiles;
 renderProfiles=async function(){
   const x=await _renderProfilesBrand.apply(this,arguments);
   const email=n('profileEmail');
   if(email){
     email.required=false;
     email.placeholder='Facultatif pour les opérateurs';
     const label=email.previousElementSibling;
     if(label&&label.classList.contains('label'))label.textContent='E-mail (facultatif)';
   }
   const name=n('profileName');
   if(name){
     const label=name.previousElementSibling;
     if(label&&label.classList.contains('label'))label.textContent='Nom utilisateur';
     name.placeholder='Ex. Emmanuelle';
   }
   return x;
 };

 const IDLE_MS=15*60*1000,IDLE_KEY='lsn-last-activity';
 let lastActivity=Number(localStorage.getItem(IDLE_KEY)||Date.now());
 let idleLogoutStarted=false,lastHeartbeat=0;
 function markActivity(){
   lastActivity=Date.now();
   if(serverReady&&lastActivity-lastHeartbeat>30000){lastHeartbeat=lastActivity;apiJson("/api/auth/activity",{method:"POST",body:"{}"}).catch(()=>statusSync("Activité non confirmée sur le serveur : vérifier la connexion.",true));}
   try{localStorage.setItem(IDLE_KEY,String(lastActivity))}catch(e){}
 }
 async function checkIdle(){
   if(idleLogoutStarted||!serverReady)return;
   if(Date.now()-lastActivity<IDLE_MS)return;
   idleLogoutStarted=true;
   try{await apiJson('/api/auth/logout',{method:'POST',body:'{}'})}finally{location.replace('/login')}
 }
 ['pointerdown','keydown','touchstart','input'].forEach(evt=>document.addEventListener(evt,markActivity,{passive:true,capture:true}));
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkIdle()});
 window.addEventListener('focus',checkIdle);
 setInterval(checkIdle,30000);
 setTimeout(()=>{decorateBrand();checkIdle()},150);
})();

// An unsuccessful write freezes workflow controls until the authoritative reload.
for(const eventName of ['click','keydown','submit'])document.addEventListener(eventName,event=>{
 if(!syncBlocked)return;
 if(event.target?.textContent==='RECHARGER LES DONNÉES')return;
 event.preventDefault();event.stopImmediatePropagation();
},true);
