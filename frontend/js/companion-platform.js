export const COMPANION_PLATFORMS=Object.freeze({'windows-x86_64':'Windows','macos-arm64':'Mac — Apple Silicon','macos-x86_64':'Mac — Intel','linux-x86_64':'Linux — Ubuntu / Mint'});

export function platformLabel(target){return COMPANION_PLATFORMS[target]??'Choose your computer';}

export function recommendPlatform({platform='',userAgent=''}={}){
 const value=platform+' '+userAgent;
 if(/iPhone|iPad|Android/i.test(value))return {os:null,targets:[]};
 if(/Mac/i.test(value))return {os:'macos',targets:['macos-arm64','macos-x86_64']};
 if(/Win/i.test(value))return {os:'windows',targets:['windows-x86_64']};
 if(/Linux/i.test(value)&&!/arm|aarch/i.test(value))return {os:'linux',targets:['linux-x86_64']};
 return {os:null,targets:[]};
}

export function initialDownload(status,browser={}){
 if(status.companionVersion)return status.download;
 const recommendation=recommendPlatform(browser);
 if(recommendation.targets.length===1){
  const target=recommendation.targets[0];
  return status.downloads?.find(d=>d.target===target)??{available:false,target};
 }
 if(recommendation.os==='macos')return {available:false,ambiguousArchitecture:true};
 // Legacy servers without a catalog still serve their existing Windows flow.
 return Array.isArray(status.downloads)?{available:false}:status.download;
}

export function downloadUrl(download){
 try{
  const url=new URL(download.url,'https://clipbot.invalid');
  if(url.origin!=='https://clipbot.invalid'||url.pathname!=='/api/companion/download'||url.hash||url.username||url.password)return null;
  if([...url.searchParams.keys()].some(key=>key!=='target')||url.searchParams.getAll('target').length>1)return null;
  const target=url.searchParams.get('target');
  if(target&&(!Object.hasOwn(COMPANION_PLATFORMS,target)||(download.target&&download.target!==target)))return null;
  if(download.target&&download.target!=='windows-x86_64'&&!target)return null;
  return url.pathname+url.search;
 }catch{return null;}
}
