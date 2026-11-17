"""Run the complete website on loopback with a separate database and no live keys."""
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
RUNTIME_NAMES=('PATH','SystemRoot','WINDIR','COMSPEC','TEMP','TMP','LOCALAPPDATA','APPDATA','USERPROFILE','PROGRAMFILES','PROGRAMFILES(X86)','NUMBER_OF_PROCESSORS')

def staging_environment(root,inherited):
    root=Path(root).resolve()
    env={name:inherited[name] for name in RUNTIME_NAMES if name in inherited}
    env.update({
        'CLIPBOT_ORIGIN':'http://127.0.0.1:8766',
        'CLIPBOT_DB_PATH':str(root/'.staging'/'clipbot.db'),
        'CLIPBOT_LOCAL_SIGNUP':'1','CLIPBOT_DEV_BYPASS':'1',
        'CLIPBOT_PUBLIC_SIGNUP':'0','CLIPBOT_ENFORCE_CUSTOMER_ACCESS':'0',
        'CLIPBOT_BILLING_MODE':'test','CLIPBOT_LIVE_BILLING_ACCEPTED':'false',
        'CLIPBOT_CUSTOMER_ANALYSIS_ENABLED':'0',
        'CLIPBOT_GLOBAL_MONTHLY_USD':'0','CLIPBOT_GLOBAL_DAILY_USD':'0',
        'PYTHONUNBUFFERED':'1',
    })
    return env

def main():
    env=staging_environment(ROOT,os.environ)
    (ROOT/'.staging').mkdir(exist_ok=True)
    print('Local ClipBot preview: http://127.0.0.1:8766',flush=True)
    print('Separate staging database. Live billing, external email and paid AI are unavailable.',flush=True)
    return subprocess.call([sys.executable,'-m','uvicorn','server.app:create_app','--factory','--host','127.0.0.1','--port','8766'],cwd=ROOT,env=env)

if __name__=='__main__':sys.exit(main())
