"""Trusted fixed-operation JSON-RPC worker. No shell or network operations."""
import json
import os
from pathlib import Path
import stat
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.tool_registry import TOOLS, metadata, validate

def safe(path):
    if path.is_symlink() or path.is_junction():
        raise ValueError('Links are not allowed.')
    if path.exists():
        info=path.lstat()
        if getattr(info,'st_file_attributes',0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('Reparse points are not allowed.')
        if path.is_file() and info.st_nlink!=1:
            raise ValueError('Linked files are not allowed.')

def execute(root,name,args):
    validate(name,args)
    for folder in [root,*root.parents]:
        safe(folder)
    target=root/('draft.txt' if name=='create_draft' else 'sample.txt')
    safe(target)
    if name=='create_draft':
        with target.open('x',encoding='utf-8') as f: f.write(args['text'])
        return 'Created draft.txt.'
    with target.open('rb') as f: data=f.read(4097)
    if len(data)>4096: raise ValueError('Sample exceeds 4 KiB.')
    text=data.decode('utf-8')
    return str(len(text.split())) if name=='count_words' else text

def main():
    request=json.loads(sys.stdin.buffer.readline(16385))
    result={'jsonrpc':'2.0','id':request.get('id')}
    try:
        if request.get('jsonrpc')!='2.0': raise ValueError('Invalid version.')
        method=request['method']
        if method=='tools/list': value=[metadata(name) for name in TOOLS]
        elif method=='tools/call':
            p=request['params'];value=execute(Path(sys.argv[1]),p['name'],p['arguments'])
        else: raise ValueError('Unknown method.')
        result['result']=value
    except (ValueError,KeyError,TypeError,OSError) as exc:
        result['error']={'code':-32602,'message':'Target already exists.' if isinstance(exc,FileExistsError) else 'Connector rejected the request.'}
    print(json.dumps(result))
if __name__=='__main__': main()

