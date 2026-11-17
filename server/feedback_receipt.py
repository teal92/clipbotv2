"""Confirm local feedback without transferring private reasons or explanations."""
import hashlib,hmac,json,re,time

def issue_receipt(store,uid,candidate_id,decision):
 if not isinstance(candidate_id,str) or not re.fullmatch(r'[a-f0-9]{32}',candidate_id) or decision not in ('approve','reject'):return None
 with store.connection() as db:device=db.execute('SELECT token FROM worker_devices WHERE user_id=? AND expires>? ORDER BY last_seen DESC LIMIT 1',(uid,time.time())).fetchone()
 if not device:return None
 payload={'candidateId':candidate_id,'userId':uid,'decision':decision,'issuedAt':int(time.time())}
 # The digest is held only by the server/device. Never return it in a receipt.
 signature=hmac.new(bytes.fromhex(device['token']),json.dumps(payload,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest()
 return {**payload,'signature':signature}
