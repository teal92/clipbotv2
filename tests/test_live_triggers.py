from worker.live_triggers import CueDetector
from worker.live_triggers import trigger_settings_ready
import pytest

def settings(**kw):return dict(beforeSeconds=20,afterSeconds=20,cooldownSeconds=60,audioEnabled=True,audioRiseDb=10,speechEnabled=True,chatEnabled=True,chatSpikeEnabled=True,chatSpikeMultiplier=3,rules=[{'phrase':'no way','source':'speech','priority':'high'},{'phrase':'clip that','source':'chat','priority':'high'}],**kw)

def test_speech_chat_rules_and_cooldown():
 d=CueDetector(settings());assert d.speech('NO WAY this happened',100)=='speech_phrase'
 assert d.chat('clip that!',101) is None
 assert d.chat('clip that!',161)=='chat_phrase'
 assert d.speech('ordinary words',230) is None

def test_sources_disabled_and_audio_baseline():
 s=settings();s.update(speechEnabled=False,chatEnabled=False,chatSpikeEnabled=False)
 d=CueDetector(s);assert d.speech('no way',100) is None;assert d.chat('clip that',100) is None
 for n in range(6):assert d.audio(-35,100+n*5) is None
 assert d.audio(-20,140)=='audio_rise'
 assert d.audio(-15,141) is None

def test_chat_spike_requires_baseline_and_bounds():
 d=CueDetector(settings())
 for n in range(30):assert d.chat('ordinary',n) is None
 found=[d.chat('ordinary',31+n*.1) for n in range(30)]
 assert 'chat_spike' in found
 assert len(d.messages)<=500


def test_phrase_priority_changes_required_repetition():
 s=settings();s['rules']=[{'phrase':'wow','source':'speech','priority':'medium'}];d=CueDetector(s)
 assert d.speech('wow',100) is None
 assert d.speech('wow',110)=='speech_phrase'
 assert d.speech('wow',180) is None

@pytest.mark.parametrize('value',[None,{},[],{'beforeSeconds':True},'bad settings'])
def test_malformed_trigger_configuration_is_not_ready(value):
 assert not trigger_settings_ready(value)

def test_trigger_configuration_rejects_malformed_bounds_and_rules():
 assert trigger_settings_ready(settings())
 for key,value in [('beforeSeconds',True),('afterSeconds',100),('speechEnabled',1),('rules',[{'phrase':'hello','source':'shell','priority':'high'}])]:
  invalid=settings();invalid[key]=value;assert not trigger_settings_ready(invalid)
