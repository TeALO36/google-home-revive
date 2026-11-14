#pragma once

// Setup page served on the fallback access point "GH-Revive Setup" (and on the LAN once connected).
// Step 1: admin password (created on first use, asked afterwards). Step 2: Wi-Fi network + key, tested live.
namespace esphome {
namespace gh_setup {

static const char SETUP_PAGE[] = R"HTML(<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GH Revive - configuration</title>
<style>
:root{--bg:#f4f2ee;--card:#fff;--ink:#1c1b19;--muted:#6b6862;--line:#d9d5ce;--accent:#1f6f5c;--bad:#a23b2a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,sans-serif}
main{max-width:440px;margin:0 auto;padding:24px 16px}h1{font-size:1.3rem;margin:0 0 4px}p{margin:0 0 16px;color:var(--muted)}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:16px}
h2{font-size:1rem;margin:0 0 12px}label{display:block;font-size:.9rem;margin:12px 0 4px}
input,select,button{width:100%;min-height:44px;font:inherit;border:1px solid var(--line);border-radius:8px;padding:8px 12px;background:#fff}
input:focus-visible,select:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
button{background:var(--accent);color:#fff;border:0;margin-top:16px;cursor:pointer}button:disabled{opacity:.5;cursor:wait}
#msg{min-height:1.5em;margin-top:12px}.bad{color:var(--bad)}.ok{color:var(--accent)}
</style></head><body><main>
<h1>GH Revive</h1><p>Configuration de l'enceinte</p>
<form id="f">
<section><h2>1. Mot de passe administrateur</h2>
<label for="admin" id="adminLabel">Mot de passe administrateur</label><input id="admin" type="password" autocomplete="new-password" required minlength="8">
<div id="confirmBox"><label for="confirm">Confirmer le mot de passe</label><input id="confirm" type="password" autocomplete="new-password" minlength="8"></div>
</section>
<section><h2>2. Réseau Wi-Fi</h2>
<label for="net">Réseau</label><select id="net"><option value="">Recherche des réseaux...</option></select>
<label for="ssid">Nom du réseau (si absent de la liste)</label><input id="ssid" autocomplete="off" maxlength="32">
<label for="key">Clé Wi-Fi</label><input id="key" type="password" autocomplete="off" maxlength="63">
<button id="go" type="submit">Tester et enregistrer</button><div id="msg" role="status"></div>
</section></form></main>
<script>
const $=id=>document.getElementById(id),msg=(t,c)=>{$('msg').textContent=t;$('msg').className=c||''};
const TEXT={connecting:['Test de la connexion...',''],connected:['Connecté. L\'enceinte annonce son adresse IP : ','ok'],
wrong_key:['Clé incorrecte. Vérifiez-la et réessayez.','bad'],not_found:['Réseau introuvable. Rapprochez l\'enceinte ou vérifiez le nom.','bad'],
unsupported:['Sécurité de ce réseau non prise en charge (WEP). Passez la box en WPA2 ou WPA3.','bad'],
failed:['La connexion a échoué. Réessayez.','bad']};
let adminSet=false;
async function status(){const s=await (await fetch('/gh/status')).json();adminSet=s.admin_set;
$('confirmBox').hidden=adminSet;$('adminLabel').textContent=adminSet?'Mot de passe administrateur':'Nouveau mot de passe administrateur (8 caractères minimum)';return s}
async function scan(){try{const l=await (await fetch('/gh/scan')).json();if(!l.length){setTimeout(scan,3000);return}
$('net').innerHTML=l.map(n=>`<option value="${encodeURIComponent(n.ssid)}">${n.ssid.replace(/</g,'&lt;')} (${n.rssi} dBm${n.secure?'':', ouvert'})</option>`).join('')}catch(e){setTimeout(scan,3000)}}
async function poll(){let s;try{s=await status()}catch(e){msg('Le point d\'accès s\'est coupé : l\'enceinte est sans doute connectée et annonce son adresse IP. Sinon, reconnectez-vous à "GH-Revive Setup".','ok');$('go').disabled=false;return}
const t=TEXT[s.state];if(!t){$('go').disabled=false;return}msg(t[0]+(s.state==='connected'?s.ip:''),t[1]);
if(s.state==='connecting')setTimeout(poll,1000);else $('go').disabled=false}
$('f').onsubmit=async e=>{e.preventDefault();const ssid=$('ssid').value||decodeURIComponent($('net').value);
if(!adminSet&&$('admin').value!==$('confirm').value){msg('Les deux mots de passe ne correspondent pas.','bad');return}
if(!ssid){msg('Choisissez un réseau.','bad');return}$('go').disabled=true;msg('Envoi...');
const q=new URLSearchParams({admin:$('admin').value,confirm:$('confirm').value,ssid,key:$('key').value});
try{const r=await (await fetch('/gh/connect?'+q)).json();if(!r.ok){msg(r.error,'bad');$('go').disabled=false;return}poll()}
catch(e){msg('Enceinte injoignable. Réessayez.','bad');$('go').disabled=false}};
status().then(scan);
</script></body></html>)HTML";

}  // namespace gh_setup
}  // namespace esphome
