export function safePreviewUrl(value){
 const url=new URL(value);
 if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||url.port!=='8767'||url.username||url.password||url.search||url.hash||!/^\/preview\/[a-f0-9]{64}$/.test(url.pathname))throw Error('Local preview is unavailable.');
 return url.href;
}

export function safeMediaUrl(value){return safePreviewUrl(value).replace('/preview/','/media/');}
