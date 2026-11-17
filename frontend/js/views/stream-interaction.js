import {escapeHtml as e} from '../ui-utils.js';
const CUES=new Set(['manual','speech_phrase','chat_phrase','chat_spike','audio_rise','capture']);
const finite=(v,min,max)=>typeof v==='number'&&Number.isFinite(v)&&v>=min&&v<=max;
export function interactionSamples(value,now=Date.now()/1000){
 const rows=Array.isArray(value?.samples)?value.samples:[];
 return rows.filter(s=>s&&finite(s.at,0,now+60)).slice(-24).map(s=>({at:s.at,audioDb:finite(s.audioDb,-100,0)?s.audioDb:null,chatMessages:Number.isInteger(s.chatMessages)&&finite(s.chatMessages,0,100000)?s.chatMessages:null,cues:Array.isArray(s.cues)?s.cues.filter(c=>CUES.has(c)).slice(0,6):[]})).sort((a,b)=>a.at-b.at);
}
export function renderStreamInteraction(monitor={},now=Date.now()/1000){
 const samples=interactionSamples(monitor.interaction,now),latest=samples.at(-1),stale=latest&&now-latest.at>20,rows=samples.filter(s=>s.at>=now-120),start=now-120;
 const x=at=>Math.max(0,Math.min(240,(at-start)*2)).toFixed(1);
 function channel(key,label,color){
  const available=rows.some(r=>r[key]!==null),last=[...rows].reverse().find(r=>r[key]!==null),old=last&&now-last.at>20;
  const maximum=Math.max(1,...rows.map(r=>r.chatMessages??0));
  const y=v=>(32-(key==='audioDb'?(v+100)/100:v/maximum)*28).toFixed(1);
  let segments=[],line=[];
  for(const r of rows){if(r[key]===null){if(line.length)segments.push(line);line=[];}else{if(line.length&&r.at-line.at(-1).at>10){segments.push(line);line=[];}line.push(r);}}
  if(line.length)segments.push(line);
  const reading=available?(key==='audioDb'?`${last.audioDb} dBFS`:`${last.chatMessages} messages / 5s`):'';
  const chatUnavailable=key==='chatMessages'&&monitor.chatStatus&&monitor.chatStatus!=='connected';
  const status=!available?'unavailable':chatUnavailable?`unavailable · last: ${reading}`:stale||old||monitor.state==='reconnecting'?`stale · last: ${reading}`:reading;
  const chart=available?`<svg viewBox="0 0 240 36" role="img" aria-label="${e(label+' activity over the last two minutes; '+status)}"><path d="M0 33H240" class="scout-interaction-baseline"/>${segments.map(group=>group.length>1?`<polyline points="${group.map(r=>x(r.at)+','+y(r[key])).join(' ')}" fill="none" stroke="${color}" stroke-width="1.6"/>`:`<circle cx="${x(group[0].at)}" cy="${y(group[0][key])}" r="1.8" fill="${color}"/>`).join('')}</svg>`:'<div class="scout-interaction-empty">No measured samples</div>';
  return `<div class="scout-interaction-channel"><div><span>${label}</span><small>${e(status)}</small></div>${chart}</div>`;
 }
 const markers=rows.flatMap(r=>r.cues.map(c=>({at:r.at,c})));
 return `<section class="scout-interaction" aria-label="Measured stream interaction"><div class="scout-interaction-heading"><strong>Stream interaction</strong><small>Last 2 minutes${stale?' · stale':''}</small></div>${channel('audioDb','Audio','#e7b64b')}${channel('chatMessages','Chat','#82b9d9')}<div class="scout-interaction-cues"><span>Capture cues</span>${markers.length?`<svg viewBox="0 0 240 16" role="img" aria-label="${e(markers.map(m=>m.c.replaceAll('_',' ')).join(', '))}">${markers.map(m=>`<circle cx="${x(m.at)}" cy="8" r="${m.c==='capture'?4:2.5}" class="${m.c==='capture'?'scout-capture-marker':'scout-cue-marker'}"><title>${e(m.c.replaceAll('_',' '))}</title></circle>`).join('')}</svg>`:'<small>No observed cues</small>'}</div><small class="scout-interaction-note">Measured audio and received chat; gaps mean missing data. Audio follows enabled cue sampling. Dots: detected cues; rings: accepted capture requests.</small></section>`;
}
