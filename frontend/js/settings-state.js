import {readStored,writeStored} from './ui-utils.js';
const KEY='clipbot-settings-v1';
// Presets are configuration drafts; the server must enforce the lower of these and plan limits.
export const SETTING_PRESETS=Object.freeze({
 paused:Object.freeze({label:'Paused — no AI spending',dailyBudget:0,maxTurns:1,maxOutputTokens:500}),
 light:Object.freeze({label:'Light — fewer analyses',dailyBudget:0.25,maxTurns:1,maxOutputTokens:500}),
 balanced:Object.freeze({label:'Balanced — everyday use',dailyBudget:0.5,maxTurns:2,maxOutputTokens:1000}),
 busy:Object.freeze({label:'Busy — more analyses',dailyBudget:1,maxTurns:3,maxOutputTokens:1500}),
});
function derive(usagePreset){return {usagePreset,mode:'review',model:'',...SETTING_PRESETS[usagePreset]};}
export const DEFAULT_SETTINGS=Object.freeze(derive('paused'));
function validate(input){
 if(!input||!Object.hasOwn(SETTING_PRESETS,input.usagePreset)||input.mode!=='review')return null;
 const value=derive(input.usagePreset);
 for(const key of ['model','dailyBudget','maxTurns','maxOutputTokens'])if(Object.hasOwn(input,key)&&input[key]!==value[key])return null;
 return value;
}
export function getSettings(storage){return validate(readStored(KEY,DEFAULT_SETTINGS,storage))??{...DEFAULT_SETTINGS};}
export function saveSettings(input,storage){
 const value=validate(input);
 return value?writeStored(KEY,{usagePreset:value.usagePreset,mode:'review'},storage):{ok:false,error:'Choose one of the listed usage presets. Custom limits and automatic approval are unavailable.'};
}
