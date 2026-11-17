"""Customer Companion setup. No external scripts, telemetry or stored pairing codes."""
from html import escape
from .version import VERSION

SETUP_JS="""const csrf=document.querySelector('meta[name=csrf]').content;
const form=document.querySelector('form'),button=form.querySelector('button');
const status=document.querySelector('#status'),result=document.querySelector('#pair-result');
let busy=false;
const text=(id,value)=>{document.querySelector(id).textContent=value;};
const percent=value=>Number.isFinite(value)&&value>=0&&value<=100?Math.round(value)+'%':'Unavailable';
async function refresh(){
 try{
  const response=await fetch('/status');if(!response.ok)throw Error();
  const s=await response.json();
  text('#connection',s.paired?'Computer connected':'Connect this computer');
  status.textContent=s.message;document.querySelector('#connection-card').className=s.paired?'card connected':'card';
  text('#pair-summary',s.paired?'Reconnect this computer':'Enter your pairing code');
  if(!s.paired)document.querySelector('details').open=true;
  const metrics=s.metrics||{};
  text('#cpu',percent(metrics.cpuPercent));text('#ram',percent(metrics.memoryPercent));
  text('#disk',Number.isFinite(metrics.freeDiskBytes)&&metrics.freeDiskBytes>=0?Math.round(metrics.freeDiskBytes/1073741824)+' GB free':'Unavailable');
  const tools=s.tools||{};text('#readiness',Object.keys(tools).length&&Object.values(tools).every(value=>value===true)?'Local processing tools are ready.':'Local processing needs attention. If you have just installed, reopen the Companion. Otherwise check for a Companion update in ClipBot.');
 }catch{ text('#connection','Companion unavailable');status.textContent='Keep the Companion running, then refresh this page.'; }
}
form.addEventListener('submit',async event=>{
 event.preventDefault();if(busy)return;
 const input=form.querySelector('[name=code]');if(!form.reportValidity())return;
 busy=true;button.disabled=true;button.textContent='Connecting…';result.textContent='Connecting this computer securely…';
 try{
  const code=input.value;input.value='';
  const response=await fetch('/pair',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({code})});
  const data=await response.json();
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Pairing did not finish. Generate a new code in ClipBot.');
  result.textContent='Computer connected. Return to ClipBot to finish setup.';document.querySelector('details').open=false;
 }catch(error){result.textContent=error.message||'Pairing did not finish. Generate a new code in ClipBot.';}
 finally{busy=false;button.disabled=false;button.textContent='Connect this computer';await refresh();}
});
refresh();setInterval(refresh,3000);
"""


def setup_html(origin,secret):
    page="""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<meta name=csrf content='__CSRF__'><title>ClipBot Companion · Connect your computer</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#080e13;color:#eef6ff}
*{box-sizing:border-box}body{max-width:900px;margin:0 auto;padding:42px 22px;line-height:1.55}
header{display:flex;align-items:center;justify-content:space-between;gap:18px;flex-wrap:wrap}
.brand{font-size:14px;font-weight:750;letter-spacing:.08em;color:#00e5dc}.version,.muted{color:#99aec1}
h1{font-size:clamp(28px,5vw,38px);line-height:1.15;margin:24px 0 14px}h2{font-size:20px;margin:0 0 10px}
p{margin:10px 0}.card{background:#101a24;border:1px solid #293c4c;border-radius:14px;padding:24px;margin:22px 0}
.connected{border-color:#00bcb4}.steps{display:flex;gap:12px;flex-wrap:wrap;padding:0;list-style:none;counter-reset:steps}
.steps li{flex:1;min-width:180px;background:#101a24;padding:16px;border-radius:10px;border:1px solid #293c4c;counter-increment:steps}
.steps li:before{content:counter(steps);color:#00e5dc;margin-right:9px;font-weight:750}
a{color:#00e5dc}.action,button{display:inline-block;background:#00ded5;color:#061316;border:0;border-radius:8px;padding:12px 18px;font:inherit;font-weight:700;text-decoration:none;cursor:pointer}
button:disabled{opacity:.6;cursor:wait}label{display:block;font-weight:600;margin-top:18px}input,select{display:block;width:100%;background:#081017;color:#eef6ff;border:1px solid #526a7e;border-radius:8px;padding:12px;font:inherit;margin:8px 0 4px}
input:focus,select:focus,button:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid #00e5dc;outline-offset:3px}
button{margin-top:20px}small{display:block;color:#99aec1}summary{cursor:pointer;font-weight:650}
.health{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:18px 0}
.health div{background:#081017;border-radius:9px;padding:16px}.health strong{display:block;font-size:22px}
#pair-result{color:#d5f7f4;min-height:1.5em;overflow-wrap:anywhere}footer{color:#99aec1;font-size:14px}
</style></head><body><header><span class=brand>CLIPBOT COMPANION</span><span class=version>Version __VERSION__</span></header>
<h1>Your computer. Your clips.</h1><p class=muted>Connect the Companion to your ClipBot account. Capture, transcription and video rendering run on this computer.</p>
<ol class=steps><li>Sign in to ClipBot</li><li>Connect this computer</li><li>Finish setup in ClipBot</li></ol>
<section class=card id=connection-card aria-labelledby=connection><h2 id=connection>Checking connection…</h2><p id=status role=status aria-live=polite>Checking the Companion on this computer.</p>
<details open><summary id=pair-summary>Enter your pairing code</summary><p>In ClipBot, open <strong>Connect Accounts → Generate Pairing Code</strong>. Paste the one-time code below. Never enter your password here.</p>
<form><label>One-time pairing code<input name=code type=password minlength=20 maxlength=100 required autocomplete=off spellcheck=false></label>
<small>Your plan still controls the number of scouts you can use. Choose your scouts and clip preferences in Streamers.</small><button>Connect this computer</button></form></details>
<p id=pair-result role=status aria-live=polite></p></section>
<section class=card><h2>Computer health</h2><p class=muted>Health readings appear while local processing is active.</p><div class=health><div>Processor use<strong id=cpu>Unavailable</strong></div><div>Memory use<strong id=ram>Unavailable</strong></div><div>Storage<strong id=disk>Unavailable</strong></div></div><p id=readiness role=status>Checking local processing tools…</p></section>
<section class=card><h2>Continue in ClipBot</h2><p>Connect your social accounts and choose a paid plan, then use <strong>Start ClipBot</strong> at the top of the website. Pairing this computer does not start monitoring or publish content.</p><a class=action href='__ORIGIN__' target=_blank rel='noopener noreferrer'>Open ClipBot</a><p><a href='https://YOUR-GITHUB-USERNAME.github.io/ClipBotV2-setup-guide/' target=_blank rel='noopener noreferrer'>Read the initial setup guide</a></p></section>
<footer>This is the Companion running locally on your computer. Your account connects to __ORIGIN__.</footer>
<script src=/setup.js></script></body></html>"""
    return page.replace('__CSRF__',escape(secret,quote=True)).replace('__VERSION__',escape(VERSION)).replace('__ORIGIN__',escape(origin,quote=True))
