"""Bounded Python/Node bridge using pure-JS Parquet and builtin GZIP."""
import json,os,shutil,subprocess
from pathlib import Path

def command(mode,path):
    node=os.environ.get('SINDHU_RESEARCH_NODE') or shutil.which('node')
    if not node:raise RuntimeError('Node executable unavailable; set SINDHU_RESEARCH_NODE')
    return [node,'--max-old-space-size=192',str(Path(__file__).with_name('parquet_bridge.cjs')),mode,str(path)]

def write_rows(path,rows):
    with subprocess.Popen(command('write',path),stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,encoding='utf-8') as process:
        try:
            for row in rows:process.stdin.write(json.dumps(row,separators=(',',':'))+'\n')
            process.stdin.close();error=process.stderr.read();code=process.wait()
        except BaseException:
            process.terminate();process.wait();raise
        if code:raise RuntimeError('Parquet writer failed: '+error[:300])

def read_rows(path):
    with subprocess.Popen(command('read',path),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8') as process:
        try:
            for line in process.stdout:yield json.loads(line)
            error=process.stderr.read();code=process.wait()
            if code:raise RuntimeError('Parquet reader failed: '+error[:300])
        finally:
            if process.poll() is None:process.terminate();process.wait()
