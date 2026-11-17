// Shared escaping for data read from storage or the future service.
export function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[character]);
}
export function readStored(key, fallback, storage) {
  try { return JSON.parse((storage ?? globalThis.localStorage)?.getItem(key) ?? 'null') ?? structuredClone(fallback); }
  catch { return structuredClone(fallback); }
}
export function writeStored(key, value, storage) {
  try {
    const target = storage ?? globalThis.localStorage;
    if (!target) throw Error('unavailable');
    target.setItem(key, JSON.stringify(value));
    return {ok:true};
  } catch { return {ok:false,error:'Browser storage is unavailable. Your changes were not saved.'}; }
}
