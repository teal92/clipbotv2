"""Local cue matching. No chat/transcript text is persisted or sent to a model."""
from collections import deque
import math,re,threading

def trigger_settings_ready(settings):
    """Reject missing/malformed remote settings instead of enabling timed capture."""
    if not isinstance(settings,dict):return False
    for key,low,high in [('beforeSeconds',10,45),('afterSeconds',5,45),('cooldownSeconds',30,300),('audioRiseDb',1,40),('chatSpikeMultiplier',2,20)]:
        if type(settings.get(key)) is not int or not low<=settings[key]<=high:return False
    if not 15<=settings['beforeSeconds']+settings['afterSeconds']<=60:return False
    if any(type(settings.get(key)) is not bool for key in ('audioEnabled','speechEnabled','chatEnabled','chatSpikeEnabled')):return False
    rules=settings.get('rules')
    if not isinstance(rules,list) or len(rules)>20:return False
    return all(isinstance(rule,dict) and set(rule)=={'phrase','source','priority'} and isinstance(rule.get('phrase'),str) and 1<=len(rule['phrase'].strip())<=80 and len(rule['phrase'])<=80 and not any(ord(c)<32 for c in rule['phrase']) and rule.get('source') in ('speech','chat','either') and rule.get('priority') in ('high','medium','low') for rule in rules)

class CueDetector:
    def __init__(self,settings):
        self.settings=dict(settings);self.last=-math.inf;self.audio_levels=deque(maxlen=12);self.messages=deque(maxlen=500);self.lock=threading.Lock();self.matches={}
    def _accept(self,kind,now):
        if now-self.last<self.settings['cooldownSeconds']:return None
        self.last=now;return kind
    def _phrase(self,text,source):
        text=' '.join(str(text)[:2000].casefold().split())
        matches=[r for r in self.settings['rules'] if r['source'] in (source,'either') and re.search(r'(?<!\w)'+re.escape(' '.join(r['phrase'].casefold().split()))+r'(?!\w)',text)]
        return matches
    def _matched(self,text,source,now):
        for rule in sorted(self._phrase(text,source),key=lambda r:{'high':0,'medium':1,'low':2}[r['priority']]):
            key=(source,rule['phrase']);history=self.matches.setdefault(key,deque(maxlen=3));history.append(now)
            while history and history[0]<now-30:history.popleft()
            if len(history)>={'high':1,'medium':2,'low':3}[rule['priority']]:return True
        return False
    def speech(self,text,now):
        with self.lock:
            if self.settings['speechEnabled'] and self._matched(text,'speech',now):return self._accept('speech_phrase',now)
    def audio(self,level,now):
        if not math.isfinite(level):return None
        with self.lock:
            baseline=sum(self.audio_levels)/len(self.audio_levels) if self.audio_levels else level
            rising=len(self.audio_levels)>=6 and level>-35 and level-baseline>=self.settings['audioRiseDb']
            self.audio_levels.append(level)
            if self.settings['audioEnabled'] and rising:return self._accept('audio_rise',now)
    def chat(self,text,now):
        with self.lock:
            self.messages.append(now)
            while self.messages and self.messages[0]<now-35:self.messages.popleft()
            if self.settings['chatEnabled'] and self._matched(text,'chat',now):return self._accept('chat_phrase',now)
            older=[n for n in self.messages if n<=now-5]
            recent=sum(n>now-5 for n in self.messages)
            baseline=len(older)/30*5
            if self.settings['chatSpikeEnabled'] and len(older)>=5 and now-older[0]>=25 and recent>=max(8,baseline*self.settings['chatSpikeMultiplier']):return self._accept('chat_spike',now)
