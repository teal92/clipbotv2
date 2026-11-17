"""Strict heartbeat telemetry bounds with no text or platform credentials."""
import math

def validate_interaction(value, now):
    def number(v, low, high):return type(v) in (int,float) and math.isfinite(v) and low<=v<=high
    if not isinstance(value,dict) or set(value)!={'samples'} or not isinstance(value['samples'],list) or len(value['samples'])>24:raise ValueError('Invalid interaction samples.')
    previous=-1
    for row in value['samples']:
        if not isinstance(row,dict) or set(row)!={'at','audioDb','chatMessages','cues'}:raise ValueError('Invalid interaction sample.')
        if not number(row['at'],0,now+60) or row['at']<=previous:raise ValueError('Invalid sample timestamp.')
        previous=row['at']
        if row['audioDb'] is not None and not number(row['audioDb'],-100,0):raise ValueError('Invalid audio sample.')
        if row['chatMessages'] is not None and (type(row['chatMessages']) is not int or not 0<=row['chatMessages']<=100000):raise ValueError('Invalid chat count.')
        cues=row['cues']
        if not isinstance(cues,list) or len(cues)>6 or any(type(c) is not str or c not in ('manual','speech_phrase','chat_phrase','chat_spike','audio_rise','capture') for c in cues) or len(set(cues))!=len(cues):raise ValueError('Invalid cue sample.')
