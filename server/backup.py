"""Encrypted logical recovery archive. Restore only to an empty isolated database."""
import json, hashlib, os
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select, DateTime
from cryptography.fernet import Fernet

FORMAT='lsn-recovery-v1'

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()

def schema_hash(metadata):
    return hashlib.sha256(canonical({t.name:[{'name':c.name,'type':str(c.type),'nullable':c.nullable} for c in t.columns] for t in metadata.sorted_tables})).hexdigest()

def snapshot(engine, metadata):
    now=datetime.now(timezone.utc)
    try:keep=now.replace(year=now.year+5)
    except ValueError:keep=now.replace(year=now.year+5,day=28)
    tables={}
    with engine.connect() as conn:
        if engine.dialect.name=='postgresql':conn=conn.execution_options(isolation_level='REPEATABLE READ')
        if engine.dialect.name=='sqlite':conn.exec_driver_sql('BEGIN')
        for table in metadata.sorted_tables:
            rows=conn.execute(select(table).order_by(table.c.id)).mappings().all()
            tables[table.name]=[{k:v.isoformat() if isinstance(v,datetime) else v for k,v in row.items()} for row in rows]
        conn.rollback()
    return {'format':FORMAT,'schemaSha256':schema_hash(metadata),'createdAt':now.isoformat(),'retainUntil':keep.isoformat(),'sourceCommit':os.getenv('RENDER_GIT_COMMIT','local'),'engine':engine.dialect.name,'tables':tables,'counts':{k:len(v) for k,v in tables.items()}}

def encrypt_snapshot(data,key):
    raw=canonical(data)
    envelope={'payload':data,'sha256':hashlib.sha256(raw).hexdigest()}
    return Fernet(key).encrypt(canonical(envelope))

def decrypt_snapshot(token,key,metadata):
    envelope=json.loads(Fernet(key).decrypt(token))
    data=envelope['payload']
    if data.get('format')!=FORMAT or data.get('schemaSha256')!=schema_hash(metadata):raise ValueError('Format ou schéma incompatible')
    if hashlib.sha256(canonical(data)).hexdigest()!=envelope.get('sha256'):raise ValueError('Empreinte de sauvegarde incorrecte')
    if set(data.get('tables',{}))!={t.name for t in metadata.sorted_tables}:raise ValueError('Sauvegarde incomplète')
    for table in metadata.sorted_tables:
        rows=data['tables'][table.name]
        if not isinstance(rows,list) or data.get('counts',{}).get(table.name)!=len(rows):raise ValueError('Comptage de sauvegarde incohérent')
        if any(set(r)!={c.name for c in table.columns} for r in rows):raise ValueError('Colonnes de sauvegarde incohérentes')
    return data

def restore_to_empty(engine,metadata,data):
    # Session/reset tokens are deliberately invalidated during recovery.
    restored={}
    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            if conn.execute(select(table.c.id).limit(1)).first() is not None:raise ValueError('Cible non vide : restauration refusée')
        for table in metadata.sorted_tables:
            rows=[] if table.name in {'sessions','password_resets'} else data['tables'][table.name]
            prepared=[]
            for row in rows:
                item=dict(row)
                for col in table.columns:
                    if isinstance(col.type,DateTime) and item[col.name] is not None:item[col.name]=datetime.fromisoformat(item[col.name])
                prepared.append(item)
            if prepared:conn.execute(table.insert(),prepared)
            restored[table.name]=len(prepared)
            if engine.dialect.name=='postgresql' and prepared:
                # All table/column identifiers originate in application metadata.
                from sqlalchemy import text
                conn.execute(text("SELECT setval(pg_get_serial_sequence(:table, 'id'), :maximum, true)"),{'table':table.name,'maximum':max(r['id'] for r in prepared)})
    return restored

def production_checks(engine):
    enabled=os.getenv('LSN_PRODUCTION','false').lower()=='true'
    if not enabled:return
    missing=[]
    if engine.dialect.name!='postgresql':missing.append('PostgreSQL requis')
    if os.getenv('COOKIE_SECURE','false').lower()!='true':missing.append('Cookie HTTPS requis')
    if not os.getenv('PUBLIC_BASE_URL','').startswith('https://'):missing.append('URL HTTPS requise')
    for name in ('LSN_BACKUP_KEY','LSN_BACKUP_STORAGE_APPROVED','LSN_RECOVERY_QUALIFIED','LSN_PHARMACEUTICAL_RELEASE'):
        if name=='LSN_BACKUP_KEY':
            if not os.getenv(name):missing.append(name+' requis')
        elif os.getenv(name,'false').lower()!='true':missing.append(name+' doit être true après qualification')
    if os.getenv('LSN_BACKUP_KEY'):
        try:Fernet(os.environ['LSN_BACKUP_KEY'])
        except (ValueError,TypeError):missing.append('Clé de sauvegarde invalide')
    if missing:raise RuntimeError('Mode production bloqué : '+', '.join(missing))

if __name__=='__main__':
    import argparse
    from sqlalchemy import create_engine
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['export','verify','restore']);parser.add_argument('path');parser.add_argument('--isolated-empty-target',action='store_true');args=parser.parse_args()
    key=os.environ.get('LSN_BACKUP_KEY')
    if not key:parser.error('LSN_BACKUP_KEY doit provenir du coffre de secrets')
    # Import models from the source application; initialisation of its source DB is read-only except existing startup migrations.
    os.environ['LSN_BACKUP_TOOL']='true'
    import app
    if args.action=='export':
        target=Path(args.path)
        with target.open('xb') as out:out.write(encrypt_snapshot(snapshot(app.engine,app.Base.metadata),key))
        target.chmod(0o600);print('Archive chiffrée créée')
    else:
        data=decrypt_snapshot(Path(args.path).read_bytes(),key,app.Base.metadata)
        if args.action=='verify':print(json.dumps({'createdAt':data['createdAt'],'retainUntil':data['retainUntil'],'counts':data['counts']}))
        else:
            url=os.environ.get('RESTORE_DATABASE_URL')
            if not url or not args.isolated_empty_target or url==app.DATABASE_URL:parser.error('Cible distincte vide et confirmation isolation requises')
            target=create_engine(url);app.Base.metadata.create_all(target);print(json.dumps(restore_to_empty(target,app.Base.metadata,data)))
