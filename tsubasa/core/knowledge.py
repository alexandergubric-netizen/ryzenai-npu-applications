"""Workspace-local knowledge index. Each source replacement is transactional."""
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
from core.file_hub import run_file_worker

AREAS=("coding","biology","chemistry","physics","mathematics")
MODEL="embed-gemma:300m"

def chunks(text):
    text=text.strip()
    for start in range(0,len(text),850):
        part=text[start:start+1000].strip()
        if part:
            yield part
        if start+1000>=len(text):
            break

def area_name(value):
    if not isinstance(value,str) or not re.fullmatch(r"[\w][\w -]{0,47}",value):
        raise ValueError("Enter an area name of 1 to 48 characters.")
    return value.casefold()

class Knowledge:
    def __init__(self,store,files):
        self.store,self.files=store,files
        with store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS kb_source(id INTEGER PRIMARY KEY,workspace TEXT NOT NULL,area TEXT NOT NULL,
            name TEXT NOT NULL,sha TEXT NOT NULL,mtime INTEGER NOT NULL,version TEXT NOT NULL,UNIQUE(workspace,area,name));
            CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks USING fts5(text,source UNINDEXED,page UNINDEXED);
            CREATE TABLE IF NOT EXISTS kb_vector(chunk INTEGER PRIMARY KEY,model TEXT,dimension INTEGER,vector TEXT);
            """)

    def inventory(self,workspace):
        with self.store.connect() as db:
            return [dict(row) for row in db.execute("SELECT area,name,sha,version FROM kb_source WHERE workspace=? ORDER BY area,name",(workspace,))]

    def source(self,workspace,name):
        path=self.files.path(self.files.root(workspace),name)
        if not path.is_file() or path.suffix.lower() not in {".pdf",".txt",".md"}:
            raise ValueError("Choose a workspace PDF, Markdown or text file.")
        return path

    def add(self,workspace,area,names,embed=None,expected=None):
        area=area_name(area)
        if not isinstance(names,list) or not 1<=len(names)<=8 or len(set(names))!=len(names):
            raise ValueError("Select one to eight distinct sources.")
        version="chunks-v1/"+(MODEL if embed else "fts5")
        updates=[]
        with self.store.connect() as db:
            for name in names:
                path=self.source(workspace,name)
                raw=path.read_bytes()
                digest=hashlib.sha256(raw).hexdigest()
                if expected is not None and digest!=expected[name]:
                    raise ValueError("Source changed after approval.")
                mtime=path.stat().st_mtime_ns
                prev=db.execute("SELECT id,sha,version FROM kb_source WHERE workspace=? AND area=? AND name=?",(workspace,area,name)).fetchone()
                if prev and prev["sha"]==digest and prev["version"]==version:
                    db.execute("UPDATE kb_source SET mtime=? WHERE id=?",(mtime,prev["id"]))
                    continue
                if path.suffix.lower()==".pdf":
                    with TemporaryDirectory(dir=path.parent) as directory:
                        snapshot=Path(directory)/"source.pdf"
                        snapshot.write_bytes(raw)
                        request={"jsonrpc":"2.0","id":"kb","method":"kb/pages","params":{"path":str(snapshot)}}
                        reply = run_file_worker(request, directory, output_limit=2000000)
                        if reply.get("id")!="kb" or "result" not in reply:
                            raise ValueError("Choose an unlocked, text-bearing PDF within the index limits.")
                        pages=reply["result"]
                else:
                    pages=[{"page":None,"text":raw.decode("utf-8-sig")}]
                parts=[(p["page"],part) for p in pages for part in chunks(p["text"])]
                if not parts or len(parts)>256:
                    raise ValueError("Choose a text-bearing source of up to 256 chunks.")
                vectors=embed([part for _,part in parts]) if embed else []
                if embed and (len(vectors)!=len(parts) or not vectors[0] or any(len(v)!=len(vectors[0]) or not all(math.isfinite(x) for x in v) for v in vectors)):
                    raise ValueError("Invalid embedding response.")
                if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                    raise ValueError("Source changed during indexing.")
                if prev:
                    self._remove(db,prev["id"])
                sid=db.execute("INSERT INTO kb_source(workspace,area,name,sha,mtime,version) VALUES(?,?,?,?,?,?)",(workspace,area,name,digest,mtime,version)).lastrowid
                for i,(page,part) in enumerate(parts):
                    cid=db.execute("INSERT INTO kb_chunks(text,source,page) VALUES(?,?,?)",(part,sid,page)).lastrowid
                    if embed:
                        v=vectors[i]
                        db.execute("INSERT INTO kb_vector VALUES(?,?,?,?)",(cid,MODEL,len(v),json.dumps(v)))
                updates.append(name)
        return {"indexed":updates,"unchanged":len(names)-len(updates),"version":version}

    @staticmethod
    def _remove(db,sid):
        db.execute("DELETE FROM kb_vector WHERE chunk IN (SELECT rowid FROM kb_chunks WHERE source=?)",(sid,))
        db.execute("DELETE FROM kb_chunks WHERE source=?",(sid,))
        db.execute("DELETE FROM kb_source WHERE id=?",(sid,))

    def remove(self,workspace,area,name):
        with self.store.connect() as db:
            row=db.execute("SELECT id FROM kb_source WHERE workspace=? AND area=? AND name=?",(workspace,area_name(area),name)).fetchone()
            if not row:
                raise ValueError("Source is not indexed in this area.")
            self._remove(db,row["id"])

    def search(self,workspace,area,query,k=5,embed=None):
        area=area_name(area)
        if not isinstance(query,str) or len(query)>500 or type(k)!=int or not 1<=k<=8:
            raise ValueError("Use a query up to 500 characters and 1 to 8 results.")
        words=[w for w in re.findall(r"\w+",query.lower()) if w not in {"what","is","in","of","the","a","an","does","how","which","for","to","are","and","when","where","who","why","was","were","did","do","can","be","it","by","or","describe","explain"} and len(w)>1][:24]
        if not words:return []
        with self.store.connect() as db:
            db.execute("BEGIN")  # Hold one source revision across ranking and citation lookup.
            lexical=[r[0] for r in db.execute("SELECT c.rowid FROM kb_chunks c JOIN kb_source s ON s.id=c.source WHERE kb_chunks MATCH ? AND s.workspace=? AND s.area=? ORDER BY bm25(kb_chunks),c.rowid LIMIT 40",(" OR ".join('"'+w+'"' for w in words),workspace,area))]
            ranks=[lexical]
            if embed:
                q=embed([query])[0]; norm=math.sqrt(sum(x*x for x in q))
                scores=[]
                for cid,raw in db.execute("SELECT v.chunk,v.vector FROM kb_vector v JOIN kb_chunks c ON c.rowid=v.chunk JOIN kb_source s ON s.id=c.source WHERE s.workspace=? AND s.area=? AND v.model=? AND v.dimension=?",(workspace,area,MODEL,len(q))):
                    vec=json.loads(raw);den=norm*math.sqrt(sum(x*x for x in vec))
                    similarity=sum(x*y for x,y in zip(q,vec))/den if den else 0
                    if similarity>=0.65:scores.append((similarity,cid))
                ranks.append([cid for _,cid in sorted(scores,reverse=True)[:40]])
            fused={}
            for ranking in ranks:
                for pos,cid in enumerate(ranking,1):fused[cid]=fused.get(cid,0)+1/(60+pos)
            hits=[]
            revisions={}
            for cid in sorted(fused,key=lambda c:(-fused[c],c)):
                row=db.execute("SELECT s.name,s.sha,c.page,c.text FROM kb_chunks c JOIN kb_source s ON s.id=c.source WHERE c.rowid=?",(cid,)).fetchone()
                name=row[0]
                if name not in revisions:
                    try:
                        revisions[name]=hashlib.sha256(self.source(workspace,name).read_bytes()).hexdigest()
                    except (OSError,ValueError):
                        revisions[name]=None
                if revisions[name]!=row[1]:
                    continue
                hits.append({"citation":len(hits)+1,"source":row[0],"sha256":row[1],"page":row[2],"excerpt":row[3]})
                if len(hits)==k:break
            return hits

