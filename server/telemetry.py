"""Bounded in-memory API timing totals; never paths, payloads or user identities."""
import os,time
from collections import deque
from threading import Lock

class Telemetry:
    def __init__(self,capacity=2000):self.samples=deque(maxlen=capacity);self.lock=Lock();self.cpu=time.process_time();self.wall=time.monotonic()
    def record(self,milliseconds,status):
        with self.lock:self.samples.append((time.monotonic(),max(0,milliseconds),status))
    def snapshot(self):
        now=time.monotonic();cpu=time.process_time()
        with self.lock:
            recent=[v for v in self.samples if v[0]>=now-60];elapsed=now-self.wall
            percent=max(0,(cpu-self.cpu)/elapsed*100) if elapsed>.01 else None;self.wall=now;self.cpu=cpu
        latencies=sorted(v[1] for v in recent);memory=None
        try:
            with open('/proc/self/statm',encoding='ascii') as handle:memory=int(handle.read().split()[1])*os.sysconf('SC_PAGE_SIZE')
        except (OSError,ValueError,IndexError,AttributeError):pass
        return {'sampleCount':len(recent),'requestsLastMinute':len(recent),'errorsLastMinute':sum(v[2]>=500 for v in recent),'medianLatencyMs':round(latencies[len(latencies)//2],2) if latencies else None,'p95LatencyMs':round(latencies[min(len(latencies)-1,int(len(latencies)*.95))],2) if latencies else None,'processCpuPercent':round(percent,2) if percent is not None else None,'processMemoryBytes':memory,'windowSeconds':60,'singleInstance':True}
