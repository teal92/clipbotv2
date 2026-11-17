"""Small native-host checks; never substitute CI for a customer's desktop test."""
import argparse
import json
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worker.platforms.identity import current_target


def validated_commit(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{40}', value):
        raise ValueError('Use the full reviewed source commit hash.')
    return value


def probe(target):
    host = current_target()
    result = {'target':target,'hostTarget':host,'passed':False,'cleanMachineAccepted':False,'checks':{'target_matches_host':host==target},'desktopChecks':'not-exercised'}
    if host != target:
        return result
    from worker.platforms.posix_integration import SingleInstance, parse_pair_link, deliver_pair_link, consume_pair_link
    from worker.credentials import save, load, delete
    with tempfile.TemporaryDirectory(prefix='clipbot-native-check-') as directory:
        # macOS exposes /var through a system symlink; use the physical temporary
        # directory before checking that our own storage hierarchy contains no links.
        root = Path(directory).resolve()
        root.chmod(0o700)
        first, second = SingleInstance(root), SingleInstance(root)
        try:
            result['checks']['single_instance'] = first.primary and not second.primary
        finally:
            first.close()
            second.close()
        code = secrets.token_urlsafe(24)
        path = root/'device.bin'
        try:
            save(path, 'https://clipbot.your-domain.example', code)
            result['checks']['protected_credentials'] = load(path, 'https://clipbot.your-domain.example') == code and load(path, 'https://other.example') is None and code.encode() not in path.read_bytes()
            delete(path, 'https://clipbot.your-domain.example')
            result['checks']['credential_deletion'] = load(path, 'https://clipbot.your-domain.example') is None
            deliver_pair_link('clipbot-companion://pair?code='+code, root)
            result['checks']['one_time_handoff'] = consume_pair_link(root) == code and consume_pair_link(root) is None
        except Exception:
            # Even keyring error text can contain a secret; return only a fixed diagnostic.
            result['checks']['protected_credentials'] = False
            result['secureStorageNote'] = 'Native keychain/keyring check failed; inspect its availability on the native runner.'
        finally:
            try:
                delete(path, 'https://clipbot.your-domain.example')
                delete(root/'pair-handoff.bin', 'https://clipbot.your-domain.example')
            except Exception:
                result['checks']['credential_cleanup'] = False
        try:
            parse_pair_link('clipbot-companion://pair?code='+code+'&command=run')
            result['checks']['hostile_link_rejected'] = False
        except ValueError:
            result['checks']['hostile_link_rejected'] = True
    result['passed'] = all(result['checks'].values())
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=['macos-arm64','macos-x86_64','linux-x86_64'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-commit')
    args = parser.parse_args()
    if args.source_commit:
        validated_commit(args.source_commit)
    try:
        result = probe(args.target)
    except Exception:
        result = {'target':args.target,'passed':False,'cleanMachineAccepted':False,'error':'Native integration probe failed; no customer or production credentials were used.'}
    if args.source_commit:
        result['sourceCommit'] = args.source_commit
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
