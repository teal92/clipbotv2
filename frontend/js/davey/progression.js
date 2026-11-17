// Server state supplies the baseline; the server rechecks every permission.
export function readDaveyProgression(form){
 const holder=form.querySelector('[data-davey-preferences]');
 if(!holder?.dataset.progression)return null;
 const old=JSON.parse(holder.dataset.progression),data=new FormData(form),settings={...old.settings};
 settings.personalContext=data.has('personalContext');
 if(form.querySelector('[name="shadowEnabled"]')){
  settings.shadowEnabled=data.has('shadowEnabled');settings.minScore=Number(data.get('minScore'));
  settings.sources=String(data.get('daveySources')??'').split(/\r?\n/).map(v=>v.trim()).filter(Boolean).map(v=>{
   if(!/^(?:twitch:[a-zA-Z0-9_]{1,35}|kick:[a-zA-Z0-9_-]{1,35})$/.test(v))throw Error('Use one source per line: twitch:login or kick:login.');
   const [platform,login]=v.split(':');return {platform,login:login.toLowerCase()};
  });
 }
 if(form.querySelector('[name="automatic"]')){
  settings.automatic=data.has('automatic');settings.rightsAccepted=data.has('rightsAccepted');
  settings.platforms=data.getAll('automaticPlatforms');settings.dailyPostLimit=Number(data.get('dailyPostLimit'));
 }
 if(!settings.personalContext)settings.shadowEnabled=settings.automatic=false;
 if(!settings.shadowEnabled)settings.automatic=false;
 return {settings,revision:old.revision};
}
