"""Immutable per-platform artifact snapshots; paths never come from request text."""
from pathlib import Path

from .companion_download import FILENAMES, OwnerInstaller
from .companion_remote_download import RemoteInstaller


class ReleaseCatalog:
    def __init__(self, root: Path):
        self.releases = {target: OwnerInstaller(root, target) for target in FILENAMES}
        for target, installer in self.releases.items():
            if target != 'windows-x86_64' and not installer.ready():
                remote = RemoteInstaller(root, target)
                if remote.ready():
                    self.releases[target] = remote

    def installer(self, target: str) -> OwnerInstaller:
        if not isinstance(target, str) or target not in self.releases:
            raise ValueError('Unsupported companion platform.')
        return self.releases[target]

    def required_version(self, target: str) -> str | None:
        installer = self.installer(target)
        return installer.metadata['version'] if installer.ready() else None
