"""Windows stays on its release; native candidates carry target-bound build metadata."""
import json
import re
from pathlib import Path


def version_for_bundle(directory):
    path = Path(directory) / 'native-release.json'
    if not path.exists():
        return '0.2.10'
    try:
        from .platforms.identity import current_target
        if path.is_symlink() or path.stat().st_size > 512:
            raise ValueError()
        value = json.loads(path.read_text(encoding='utf-8'))
        if set(value) != {'version','target'} or value['target'] != current_target() or not isinstance(value['version'],str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.]+)?',value['version']):
            raise ValueError()
        return value['version']
    except (OSError, ValueError, TypeError):
        raise RuntimeError('Companion release metadata is invalid. Reinstall the verified package.') from None


VERSION = version_for_bundle(Path(__file__).parent)
