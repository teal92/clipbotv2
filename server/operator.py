"""Host-operator CLI only; never served as an HTTP administration endpoint."""
import argparse,json,sqlite3,os,re,getpass,sys
from pathlib import Path
from contextlib import closing
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]

def readonly(path):
    path=Path(path).resolve(strict=True)
    return sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)

def validate(db):
    if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity check failed.')
    required={'users','sessions','preferences','coverage','jobs','guards'}
    tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required<=tables:raise ValueError('Not a ClipBot service database.')

def backup_database(source,destination):
    destination=Path(destination).resolve()
    if destination.is_relative_to((ROOT/'frontend').resolve()):raise ValueError('Never place private databases in the publicly served frontend folder.')
    if destination.exists():raise FileExistsError('Destination exists. Choose a new backup filename.')
    with closing(readonly(source)) as incoming:
        validate(incoming)
        # Exclusive file creation prevents replacing a live database or an existing backup.
        with destination.open('xb'):pass
        try:
            with closing(sqlite3.connect(destination)) as outgoing:
                incoming.backup(outgoing)
                validate(outgoing)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    return destination

def restore_database(source,destination):
    # Restores to a NEW path only. Switching a running service is a separate operator step.
    return backup_database(source,destination)

def list_reports(database,limit=50):
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('Choose a report limit from 1 to 100.')
    with closing(readonly(database)) as db:
        db.row_factory=sqlite3.Row
        rows=db.execute('SELECT r.id,r.created,r.data,u.email FROM reports r JOIN users u ON u.id=r.user_id ORDER BY r.created DESC LIMIT ?',(limit,)).fetchall()
    return [{'reference':row['id'],'created':datetime.fromtimestamp(row['created'],timezone.utc).isoformat(),'accountEmail':row['email'],'report':json.loads(row['data'])} for row in rows]

def create_test_account(database,email,name,password,confirmation):
    from .network_check import key_shape
    from .store import Store
    if key_shape(os.getenv('STRIPE_SECRET_KEY',''))!='sandbox_format' or os.getenv('CLIPBOT_LOCAL_SIGNUP')=='1' or os.getenv('CLIPBOT_DEV_BYPASS')=='1':raise ValueError('Requires sandbox billing with public signup and development bypass disabled.')
    path=Path(database).resolve(strict=True)
    with closing(readonly(path)) as db:validate(db)
    email=email.strip().lower();name=name.strip()
    if len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or email=='clipbot-local-development@example.invalid':raise ValueError('Enter a valid account email address.')
    if not 1<=len(name)<=80:raise ValueError('Name must contain 1 to 80 characters.')
    if not 12<=len(password)<=128 or password.isspace():raise ValueError('Choose a password with 12 to 128 characters.')
    if password!=confirmation:raise ValueError('Passwords did not match. No account created.')
    try:return Store(path).create_user(email,password,name)
    except sqlite3.IntegrityError:raise ValueError('That account already exists. This command never changes an existing password.')

def main():
    parser=argparse.ArgumentParser(description='ClipBot host-operator tools. Reports and backups contain private account data.')
    parser.add_argument('--database',default=os.getenv('CLIPBOT_DB_PATH',str(ROOT/'server/data/clipbot.db')))
    commands=parser.add_subparsers(dest='command',required=True)
    reports=commands.add_parser('reports');reports.add_argument('--limit',type=int,default=50)
    backup=commands.add_parser('backup');backup.add_argument('destination')
    restore=commands.add_parser('restore');restore.add_argument('destination')
    commands.add_parser('create-test-account',help='Interactive private sandbox account; no admin access or paid coverage.')
    args=parser.parse_args()
    if args.command=='create-test-account':
        if not sys.stdin.isatty():parser.error('Use an interactive host Shell so password entry stays hidden.')
        email=input('Your test account email: ')
        name=input('Display name: ')
        password=getpass.getpass('Choose a password (at least 12 characters): ')
        confirmation=getpass.getpass('Confirm password: ')
        try:create_test_account(args.database,email,name,password,confirmation)
        except (ValueError,FileNotFoundError) as error:parser.error(str(error))
        finally:password='';confirmation=''
        print('Private sandbox account created. Sign in at your ClipBot domain. No plan or AI allowance has been granted.')
    elif args.command=='reports':print(json.dumps(list_reports(args.database,args.limit),indent=2,ensure_ascii=True))
    else:
        target=Path(args.destination).resolve()
        if not target.is_relative_to((ROOT/'server/data').resolve()):parser.error('Store private backup and restore files under clipbot-saas/server/data.')
        operation=backup_database if args.command=='backup' else restore_database
        operation(args.database,target);print('Verified database copy saved to '+str(target))
if __name__=='__main__':main()
