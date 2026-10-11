"""Portable identity for the sources deployed by the handoff upgrade."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def source_hash():
    roots = ['mall-ai-service/app', 'mall-ai-web/src',
             'mall2/mall-portal/src/main', 'mall2/mall-admin/src/main',
             'mall2/document/sql/migrations']
    files = {path for root in roots for path in (ROOT/root).rglob('*')
             if path.is_file() and '__pycache__' not in path.parts
             and path.suffix in {'.py','.java','.xml','.yml','.yaml','.sql','.vue','.ts','.css','.json'}}
    files.update(ROOT/path for path in ['docker-compose.yml','mall-ai-web/nginx.conf',
        'mall-ai-service/Dockerfile','mall-ai-web/Dockerfile'])
    digest=hashlib.sha256()
    for path in sorted(files,key=lambda item:item.relative_to(ROOT).as_posix()):
        digest.update(path.relative_to(ROOT).as_posix().encode()+b'\0')
        digest.update(path.read_bytes().replace(b'\r\n',b'\n')+b'\0')
    return digest.hexdigest()

if __name__=='__main__':
    print(source_hash())
