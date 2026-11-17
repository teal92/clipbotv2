"""Fail closed when a companion bundle contains customer, credential or media data."""
from pathlib import Path


def audit_bundle(directory,*,allow_internal_links=False):
    root=Path(directory)
    if root.is_symlink() or not root.is_dir():return ['Bundle directory is missing or unsafe.']
    root=root.resolve()
    forbidden={'device.bin','pair-handoff.bin','transcript.json','candidate.json','artifact-recovery.json','job.json','feedback.json'}
    media={'.mp4','.mkv','.webm','.wav','.mov','.mp3','.ts'}
    private_suffixes={'.db','.cbk','.cbrk','.pfx','.p12','.key'}
    private_directories={'personal-memory','jobs','captures','backups'}
    errors=[];files=0
    try:
        for file in root.rglob('*'):
            relative=file.relative_to(root)
            linked=file.is_symlink() or (hasattr(file,'is_junction') and file.is_junction())
            if not file.resolve().is_relative_to(root) or linked and not allow_internal_links:
                errors.append('Unsafe bundle link: '+str(relative));continue
            if not file.is_file():continue
            files+=1;name=file.name.lower()
            if name in forbidden or name.startswith('.env') or file.suffix.lower() in media|private_suffixes or name.endswith(('.db-wal','.db-shm')) or private_directories.intersection(part.lower() for part in relative.parts[:-1]):
                errors.append('Forbidden bundle file: '+str(relative))
    except (OSError,RuntimeError):errors.append('Bundle could not be completely inspected.')
    if not files:errors.append('Bundle contains no files.')
    return errors

if __name__=='__main__':
    import sys
    errors=audit_bundle(sys.argv[1])
    if errors:print('\n'.join(errors));raise SystemExit(1)
    print('Bundle content audit passed.')
