from pathlib import Path
import json
import subprocess
import sys
import pytest
from tools.dependency_policy import verify_requirements
def test_dependency_policy_rejects_hallucinated_names_urls_and_unpinned_versions(tmp_path):
 allowed={'anthropic','fastapi'}
 for value in ['imaginary-ai-helper==1.0 --hash=sha256:'+'a'*64,'fastapi>=1.0','git+https://evil.example/helper']:
  p=tmp_path/'requirements.txt';p.write_text(value)
  with pytest.raises(ValueError):verify_requirements(p,allowed)
 p.write_text('fastapi==1.0 --hash=sha256:'+'a'*64)
 assert verify_requirements(p,allowed)=={'fastapi'}


def test_reviewed_version_cannot_change_without_policy_review(tmp_path):
 p=tmp_path/'requirements.txt';p.write_text('fastapi==99.0 --hash=sha256:'+'a'*64)
 with pytest.raises(ValueError):verify_requirements(p,{'fastapi':'0.136.0'})


@pytest.mark.parametrize('bootstrap', [
 'pip==25.0.1 --hash=sha256:'+'a'*64,
 'unreviewed-installer==1.0 --hash=sha256:'+'a'*64,
 '--index-url https://unreviewed.example/simple\npip==26.2.1 --hash=sha256:'+'a'*64,
])
def test_build_policy_rejects_unreviewed_bootstrap_before_install(tmp_path, bootstrap):
 """Exercise the actual pre-install entry point with an unsafe build lock."""
 (tmp_path/'tools').mkdir()
 (tmp_path/'packaging').mkdir()
 policy=Path(__file__).resolve().parents[1]/'tools'/'dependency_policy.py'
 (tmp_path/'tools'/'dependency_policy.py').write_text(policy.read_text())
 (tmp_path/'tools'/'approved-packages.json').write_text(json.dumps({'fastapi':'0.136.0'}))
 (tmp_path/'requirements.txt').write_text('fastapi==0.136.0 --hash=sha256:'+'a'*64)
 (tmp_path/'packaging'/'server-build-tools.lock').write_text(bootstrap)
 result=subprocess.run([sys.executable,str(tmp_path/'tools'/'dependency_policy.py')],capture_output=True,text=True)
 assert result.returncode != 0, 'Build accepted an unreviewed bootstrap lock'
