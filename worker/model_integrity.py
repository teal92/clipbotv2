"""Immutable model snapshot hashes; verify before native model loading."""
import hashlib
from pathlib import Path

MODEL_FILES={
 'config.json':'56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a',
 'model.bin':'d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9',
 'tokenizer.json':'fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab',
 'vocabulary.txt':'34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913'}


def verify_model(directory):
    base=Path(directory)
    if base.is_symlink() or not base.is_dir():raise ValueError('Model integrity check failed. Reinstall the verified model.')
    root=base.resolve()
    try:
        for entry in root.iterdir():
            if entry.name not in MODEL_FILES and not (entry.name=='.cache' and entry.is_dir() and not entry.is_symlink()):
                raise ValueError('Model integrity check failed. Unexpected model configuration.')
    except OSError:raise ValueError('Model integrity check failed. Reinstall the verified model.') from None
    for name,digest in MODEL_FILES.items():
        path=root/name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):raise ValueError('Model integrity check failed. Reinstall the verified model.')
        checksum=hashlib.sha256()
        try:
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):checksum.update(chunk)
        except OSError:raise ValueError('Model integrity check failed. Reinstall the verified model.') from None
        if checksum.hexdigest()!=digest:raise ValueError('Model integrity check failed. Reinstall the verified model.')
