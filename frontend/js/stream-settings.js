import {api} from './service-state.js';
export async function saveStreamSettings(draft,send=api){
 const steps=[['Clip controls','/api/scouts/controls',draft.controls],['Scout allocation','/api/scouts',draft.configuration],['Clip triggers','/api/scouts/triggers',draft.triggers],['Davey preferences','/api/davey',draft.preferences]];
 const saved=[];
 for(const [label,path,body] of steps){
  try{await send(path,{method:'PUT',body});saved.push(label);}
  catch(error){throw Error(`${label} were not saved: ${error.message}. ${saved.length?'Already saved: '+saved.join(', ')+'.':'No settings were saved.'} Review your entries and save again.`);}
 }
 return {ok:true};
}
