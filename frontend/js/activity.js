import {readStored,writeStored} from './ui-utils.js';
let activityScope='anonymous';
export function setActivityScope(value){activityScope=typeof value==='string'&&/^[a-zA-Z0-9_-]{1,100}$/.test(value)?value:'anonymous';}
const activityKey=()=> 'clipbot-activity-v2:'+activityScope;
export const MAX_ACTIVITY=200;
export const ACTIVITY_LEVELS=Object.freeze(['debug','info','warning','error']);
export const ACTIVITY_SOURCES=Object.freeze(['ui','davey','settings','processing','publishing','service','scouting','capture','transcription','rendering','companion']);
// Both persisted diagnostics and console output pass through this redaction boundary.
export function redact(message){
 return String(message)
 .replace(/https?:\/\/[^\s<>"']+/gi,value=>{try{const url=new URL(value);url.username='';url.password='';url.search='';url.hash='';return url.href;}catch{return '[REDACTED URL]';}})
 .replace(/\bBearer\s+[^\s,;]+/gi,'Bearer [REDACTED]')
 .replace(/\b(?:sk-ant-|sk-proj-)[a-zA-Z0-9_-]+/g,'[REDACTED]')
 .replace(/(["'])([\w-]*(?:key|token|password|secret|authorization|transcript|subtitles|segments|capability|pairingcode|ticket)[\w-]*)\1\s*:\s*(["'])(?:\\.|(?!\3).)*\3/gi,'$1$2$1:$3[REDACTED]$3')
 .replace(/\b([\w-]*(?:key|token|password|secret|authorization|capability|pairingcode|ticket)[\w-]*)\s*[:=]\s*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;]+)/gi,'$1=[REDACTED]')
 .replace(/\b([\w-]*(?:transcript|subtitles|segments)[\w-]*)["']?\s*[:=]\s*[^\r\n]*/gi,'$1=[REDACTED]')
 .slice(0,1000);
}
function safeDetails(details){
 if(!details||typeof details!=='object'||Array.isArray(details))return {};
 const numbers={candidateScore:[0,100],scoreThreshold:[0,100],minClipSeconds:[15,60],maxClipSeconds:[15,60],candidateMillis:[15000,60000],responseChars:[0,1000000],textBlocks:[0,1000],parsePosition:[0,1000000],parseLine:[1,1000000],parseColumn:[1,1000000]};
 const enums={monitorState:['connecting','monitoring','reconnecting'],chatStatus:['connecting','connected','unavailable','disabled'],speechStatus:['active','waiting','unavailable','disabled'],stopReason:['end_turn','max_tokens','stop_sequence','tool_use','pause_turn','refusal','other'],outputShape:['empty','fenced','plain'],failureReason:['json_decode','ambiguous_json','duplicate_key','candidate_schema','timestamp_type','timestamp_bounds','clip_length','score','metadata_title','metadata_caption','metadata_rationale','stop_reason','response_size']};
 return Object.fromEntries(Object.entries(details).filter(([key,value])=>key==='companionVersion'?typeof value==='string'&&value.length<=40&&/^[0-9]+\.[0-9]+\.[0-9]+(?:-beta)?$/.test(value):numbers[key]?Number.isSafeInteger(value)&&value>=numbers[key][0]&&value<=numbers[key][1]:enums[key]?.includes(value)));
}
export function normalizeActivity(entry){
 if(!entry||typeof entry.message!=='string'||!ACTIVITY_LEVELS.includes(entry.level)||!ACTIVITY_SOURCES.includes(entry.source))return null;
 return {id:typeof entry.id==='string'||Number.isSafeInteger(entry.id)?redact(entry.id).slice(0,100):globalThis.crypto.randomUUID(),level:entry.level,source:entry.source,message:redact(entry.message),...(entry.details?{details:safeDetails(entry.details)}:{}),createdAt:Number.isFinite(Date.parse(entry.createdAt))?new Date(entry.createdAt).toISOString():new Date().toISOString()};
}
export function getActivity(storage){
 const saved=readStored(activityKey(),[],storage);if(!Array.isArray(saved))return [];
 const unique=new Map();for(const entry of saved){const value=normalizeActivity(entry);if(value)unique.set(value.id,value);}return [...unique.values()].slice(-MAX_ACTIVITY);
}
function saveActivities(values,storage){
 const existing=getActivity(storage),ids=new Set(existing.map(v=>v.id)),fresh=[];
 for(const value of values){if(!ids.has(value.id)){ids.add(value.id);fresh.push(value);}}
 if(!fresh.length)return {ok:true,duplicate:true};
 const result=writeStored(activityKey(),[...existing,...fresh].slice(-MAX_ACTIVITY),storage);
 for(const value of fresh)globalThis.console?.debug?.('[ClipBot]',value.level,value.source,value.message);
 return result;
}
export function appendActivities(entries,storage){
 if(!Array.isArray(entries))return {ok:false,error:'Invalid activity batch.'};
 return saveActivities(entries.slice(-MAX_ACTIVITY).map(normalizeActivity).filter(Boolean),storage);
}
export function appendActivity(entry,storage){
 const value=normalizeActivity({...entry,level:entry?.level??'info',source:entry?.source??'ui'});
 return value?saveActivities([value],storage):{ok:false,error:'Invalid activity entry.'};
}
export function clearActivity(storage){return writeStored(activityKey(),[],storage);}
export function filterActivity(entries,{level='all',source='all',search=''}={}){
 const term=String(search).toLowerCase();return entries.filter(entry=>(level==='all'||entry.level===level)&&(source==='all'||entry.source===source)&&`${entry.message} ${entry.source}`.toLowerCase().includes(term));
}
