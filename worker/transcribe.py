"""Local timestamped Whisper transcription; no network or implicit model downloads."""
import math
from pathlib import Path

class TranscriptionError(ValueError):pass

def load_model(directory):
    from .model_integrity import verify_model
    try:verify_model(directory)
    except ValueError as error:raise TranscriptionError(str(error)) from None
    from faster_whisper import WhisperModel
    if not (Path(directory)/'model.bin').is_file():raise TranscriptionError('Download the local transcription model before monitoring.')
    return WhisperModel(str(directory),device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)

def transcribe(media_path,model,duration=None):
    if duration is not None and (type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=305):raise TranscriptionError('Invalid captured media duration.')
    segments,_=model.transcribe(str(Path(media_path).resolve()),vad_filter=True,beam_size=1,word_timestamps=False)
    result=[];total=0
    for segment in segments:
        text=segment.text.strip();start=float(segment.start);end=float(segment.end)
        if not text:continue
        if not math.isfinite(start) or not math.isfinite(end) or not 0<=start<end<=305 or len(text)>500:raise TranscriptionError('Local transcription returned invalid timestamps.')
        if duration is not None and end>duration:
            if end-duration>1 or start>=duration:raise TranscriptionError('Local transcription exceeds captured media duration.')
            end=duration
        total+=len(text)
        if len(result)>=200 or total>10000:raise TranscriptionError('Local transcript exceeds analysis limits.')
        result.append({'start':start,'end':end,'text':text})
    return result
