"""Explicit local model setup; run only after disclosing the download."""
from pathlib import Path
REVISION='ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66'
def download(directory):
    from huggingface_hub import snapshot_download
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True)
    snapshot_download('Systran/faster-whisper-base',revision=REVISION,local_dir=root,allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.txt'],token=False)
    from .transcribe import load_model
    load_model(root)
    return root
if __name__=='__main__':
    download(Path(__file__).parent/'data'/'models'/'base')
    print('Local transcription model is ready.')
