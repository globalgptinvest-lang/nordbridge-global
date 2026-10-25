"""Run as root on the authorized VPS; preserves existing databases/services."""
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time

SOURCE_B64 = '__DIRECTOR_SOURCE__'

def run(args, stdin=None, timeout=120):
    p=subprocess.run(args,input=stdin,text=True,capture_output=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError('command_failed:'+args[0]+':'+str(p.returncode))
    return p.stdout

def secure(path,text,mode=0o600):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(text);os.chmod(tmp,mode);os.replace(tmp,path)

def main():
    os.umask(0o077)
    if os.geteuid()!=0:raise RuntimeError('root_required')
    root=Path('/opt/nordbridge-director');root.mkdir(mode=0o755,exist_ok=True)
    backup=Path('/var/backups/nordbridge-director')/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True,mode=0o700)
    caddy=Path('/opt/nordbridge-office/caddy/Caddyfile')
    shutil.copy2(caddy,backup/'Caddyfile')
    for f in root.iterdir():
        if f.is_file():shutil.copy2(f,backup/f.name)
    # A fresh full SQL backup immediately before adding the dedicated schema.
    db='nordbridge-crm-db-1'
    info=json.loads(run(['docker','inspect',db]))[0]
    env=dict(x.split('=',1) for x in info['Config']['Env'] if '=' in x)
    admin=env.get('POSTGRES_USER','postgres')
    dump=run(['docker','exec',db,'pg_dumpall','-U',admin],timeout=180)
    secure(backup/'crm-before.sql',dump)
    print('PRECHANGE_BACKUP=PASS path='+str(backup),flush=True)
    envpath=root/'director.env'
    if envpath.exists():
        config=dict(line.split('=',1) for line in envpath.read_text().splitlines() if '=' in line)
        password=config['DATABASE_URL'].split(':',2)[2].split('@',1)[0]
    else:
        password=secrets.token_hex(32);owner=secrets.token_urlsafe(24);salt=secrets.token_hex(16)
        config={'DATABASE_URL':f'postgresql://nb_director:{password}@nordbridge-crm-db-1:5432/nordbridge',
          'DIRECTOR_ORIGIN':'https://office.57.129.182.200.sslip.io',
          'DIRECTOR_KEY':secrets.token_hex(32),'OWNER_SALT':salt,
          'OWNER_HASH':hashlib.pbkdf2_hmac('sha256',owner.encode(),bytes.fromhex(salt),600000).hex(),
          'OLLAMA_URL':'http://ollama:11434'}
        secure('/root/nordbridge-director-owner.txt','URL: '+config['DIRECTOR_ORIGIN']+'\nPassword: '+owner+'\n')
        secure(envpath,'\n'.join(k+'='+v for k,v in config.items())+'\n')
    sql=f"""DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='nb_director') THEN
      CREATE ROLE nb_director LOGIN PASSWORD '{password}'; END IF; END $$;
      GRANT CONNECT ON DATABASE nordbridge TO nb_director;
      CREATE SCHEMA IF NOT EXISTS director AUTHORIZATION nb_director;
      GRANT USAGE ON SCHEMA public TO nb_director;
      GRANT SELECT ON public.website_leads TO nb_director;"""
    run(['docker','exec','-i',db,'psql','-U',admin,'-d','nordbridge','-v','ON_ERROR_STOP=1'],sql)
    secure(root/'director.py',base64.b64decode(SOURCE_B64).decode(),0o644)
    compose='''services:
  director:
    image: nordbridge-office-core
    user: "65534:65534"
    command: ["uvicorn", "director:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
    env_file: [director.env]
    volumes: ["./director.py:/app/director.py:ro"]
    restart: unless-stopped
    mem_limit: 512m
    cpus: 0.75
    pids_limit: 128
    read_only: true
    tmpfs: ["/tmp:size=32m,mode=1777"]
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    networks: [crm,office]
    logging:
      driver: json-file
      options: {max-size: "5m", max-file: "3"}
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
networks:
  crm: {external: true, name: nordbridge-crm_private}
  office: {external: true, name: nordbridge-office_default}
'''
    secure(root/'compose.yaml',compose)
    dc=['docker','compose','-p','nordbridge-director','-f',str(root/'compose.yaml')]
    run(dc+['config','--quiet'])
    run(dc+['run','--rm','--no-deps','director','python3','-c',
      "import director; assert len(director.ROLES)==14; assert 'BoVendia' in director.POLICY; print('IMPORT_PASS')"])
    run(dc+['up','-d','--no-build'])
    for attempt in range(24):
        try:
            run(['docker','exec','nordbridge-director-director-1','python3','-c',
              "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/health').status==200"],timeout=10)
            break
        except Exception:time.sleep(2)
    else:raise RuntimeError('director_health_failed')
    old=caddy.read_text()
    import re
    new=re.sub(r'----crm\.57\.129\.182\.200\.sslip\.io\s*\{\s*@health path /health\s*\}\s*','',old)
    host='office.57.129.182.200.sslip.io'
    if host not in new:
        new+='\n'+host+' {\n encode zstd gzip\n @internal path /internal/*\n handle @internal { respond "Not found" 404 }\n handle { reverse_proxy nordbridge-director-director-1:8000 }\n}\n'
    if new!=old:
        secure(caddy,new,0o644)
        try:
            run(['docker','exec','nordbridge-office-caddy-1','caddy','validate','--config','/etc/caddy/Caddyfile'])
            run(['docker','exec','nordbridge-office-caddy-1','caddy','reload','--config','/etc/caddy/Caddyfile'])
        except Exception:
            secure(caddy,old,0o644)
            run(['docker','exec','nordbridge-office-caddy-1','caddy','reload','--config','/etc/caddy/Caddyfile'])
            raise
    print('DIRECTOR_DEPLOY=PASS; owner credentials=/root/nordbridge-director-owner.txt; no password published',flush=True)
    print('COMPOSE_CONFIG=PASS; DIRECTOR_HEALTH=PASS; CADDY_VALIDATE=PASS',flush=True)

if __name__=='__main__':main()
