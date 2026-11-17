"""Bounded numeric observations; never retain chat or transcript contents."""
from collections import deque
import math, threading

class InteractionWindow:
    def __init__(self):
        self.samples=deque(maxlen=24);self.lock=threading.Lock()
    def _row(self, at):
        at=int(at//5)*5
        for row in self.samples:
            if row['at']==at:return row
        if self.samples and at<self.samples[-1]['at']:return None
        if not self.samples or self.samples[-1]['at']!=at:
            self.samples.append({'at':at,'audioDb':None,'chatMessages':None,'cues':[]})
        return self.samples[-1]
    def observe(self, at, chat_connected=False):
        with self.lock:
            row=self._row(at)
            if row is not None and chat_connected and row['chatMessages'] is None:row['chatMessages']=0
    def audio(self, level, at):
        if type(level) not in (int,float) or not math.isfinite(level):return
        with self.lock:
            row=self._row(at)
            if row is not None:row['audioDb']=round(max(-100,min(0,level)),2)
    def chat(self, at):
        with self.lock:
            row=self._row(at)
            if row is not None:row['chatMessages']=min(100000,(row['chatMessages'] or 0)+1)
    def cue(self, kind, at):
        if kind not in ('manual','speech_phrase','chat_phrase','chat_spike','audio_rise','capture'):return
        with self.lock:
            row=self._row(at)
            if row is not None and kind not in row['cues']:row['cues'].append(kind)
    def snapshot(self):
        with self.lock:return {'samples':[{**s,'cues':list(s['cues'])} for s in self.samples]}
