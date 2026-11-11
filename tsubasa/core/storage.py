"""Transactional local chat storage. No model-invoked file access."""
import json, sqlite3, uuid
from contextlib import contextmanager
from core.config import APP_NAME
from pathlib import Path

DEFAULTS = {'assistant_name':APP_NAME,'user_call_name':'you','tone':'brief and concrete','language':'English','theme':'dark',
            'about_me':'','instructions':''}
# Free-text settings: may be empty and longer; together with workspace instructions they go into every system prompt.
LONG = {'about_me':1500,'instructions':2000}
WORKSPACE_LIMIT = 2000
class Store:
    def __init__(self, home):
        Path(home).mkdir(parents=True,exist_ok=True)
        self.path=Path(home)/'chats.sqlite3'
        with self.connect() as db:
            if db.execute('PRAGMA user_version').fetchone()[0] > 1:
                raise RuntimeError('This chat database requires a newer version of Tsubasa.')
            db.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, workspace TEXT NOT NULL REFERENCES workspaces(id), title TEXT NOT NULL, model TEXT NOT NULL, think INTEGER NOT NULL DEFAULT 0, thorough INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, chat TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, thinking TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'complete');
            PRAGMA user_version=1;''')
            db.execute('INSERT OR IGNORE INTO settings VALUES(1,?)',(json.dumps(DEFAULTS),))
            if 'instructions' not in {r[1] for r in db.execute('PRAGMA table_info(workspaces)')}:
                db.execute("ALTER TABLE workspaces ADD COLUMN instructions TEXT NOT NULL DEFAULT ''")
            db.execute("INSERT OR IGNORE INTO workspaces(id,name) VALUES('default','Personal')")
            db.execute("UPDATE messages SET state='interrupted' WHERE state='streaming'")
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()
    @staticmethod
    def _settings(db):
        return {**DEFAULTS,**json.loads(db.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])}
    def state(self):
        with self.connect() as db:
            return {'settings':self._settings(db),'workspaces':[dict(r) for r in db.execute('SELECT * FROM workspaces ORDER BY rowid')],'chats':[dict(r) for r in db.execute('SELECT * FROM chats ORDER BY rowid DESC')]}
    def chat(self, cid):
        with self.connect() as db:
            chat=db.execute('SELECT * FROM chats WHERE id=?',(cid,)).fetchone()
            if chat is None: raise ValueError('Chat not found.')
            return {**dict(chat),'messages':[dict(r) for r in db.execute('SELECT * FROM messages WHERE chat=? ORDER BY id',(cid,))]}
    def mutate(self, body):
        action=body.get('action')
        with self.connect() as db:
            if action=='settings':
                value=body.get('settings')
                if not isinstance(value,dict) or not set(DEFAULTS)-set(LONG)<=set(value)<=set(DEFAULTS):raise ValueError('Invalid settings.')
                value={**{k:'' for k in LONG},**value}
                if any(not isinstance(v,str) or not v.strip() or len(v)>100 for k,v in value.items() if k not in LONG):raise ValueError('Name, tone and language need 1–100 characters.')
                for k,limit in LONG.items():
                    if not isinstance(value[k],str) or len(value[k])>limit:raise ValueError(f'Keep this text under {limit:,} characters.')
                    value[k]=value[k].strip()
                if value['theme'] not in ('dark','light','bitmap'):raise ValueError('Invalid theme.')
                db.execute('UPDATE settings SET value=? WHERE id=1',(json.dumps(value),))
            elif action=='workspace':
                name=body.get('name','')
                if not isinstance(name,str) or not 1<=len(name.strip())<=60:raise ValueError('Workspace name must contain 1–60 characters.')
                cid=uuid.uuid4().hex;db.execute('INSERT INTO workspaces(id,name) VALUES(?,?)',(cid,name.strip()));return {'id':cid}
            elif action=='chat':
                cid=uuid.uuid4().hex
                db.execute('INSERT INTO chats(id,workspace,title,model) VALUES(?,?,?,?)',(cid,body.get('workspace','default'),'New chat',body.get('model','qwen3-it:4b')));return {'id':cid}
            elif action=='options':
                if type(body.get('think')) is not bool or type(body.get('thorough')) is not bool:raise ValueError('Invalid chat options.')
                db.execute('UPDATE chats SET model=?,think=?,thorough=? WHERE id=?',(body['model'],body['think'],body['thorough'],body['id']))
            elif action=='delete':db.execute('DELETE FROM chats WHERE id=?',(body.get('id'),))
            elif action=='workspace_instructions':
                text=body.get('instructions','')
                if not isinstance(text,str) or len(text)>WORKSPACE_LIMIT:raise ValueError(f'Keep workspace instructions under {WORKSPACE_LIMIT:,} characters.')
                if not db.execute('UPDATE workspaces SET instructions=? WHERE id=?',(text.strip(),body.get('id'))).rowcount:raise ValueError('Unknown workspace.')
            elif action=='rename_workspace':
                name=body.get('name','')
                if not isinstance(name,str) or not 1<=len(name.strip())<=60:raise ValueError('Workspace name must contain 1–60 characters.')
                if not db.execute('UPDATE workspaces SET name=? WHERE id=?',(name.strip(),body.get('id'))).rowcount:raise ValueError('Unknown workspace.')
            elif action=='delete_workspace':
                # Its chats go with it; files Tsubasa saved for it stay on disk. Personal always stays.
                wid=body.get('id')
                if wid=='default':raise ValueError('The Personal workspace cannot be deleted.')
                if not db.execute('SELECT 1 FROM workspaces WHERE id=?',(wid,)).fetchone():raise ValueError('Unknown workspace.')
                db.execute('DELETE FROM messages WHERE chat IN (SELECT id FROM chats WHERE workspace=?)',(wid,))
                db.execute('DELETE FROM chats WHERE workspace=?',(wid,))
                db.execute('DELETE FROM workspaces WHERE id=?',(wid,))
            else:raise ValueError('Unknown storage action.')
        return {'ok':True}
    def begin(self,cid,text):
        with self.connect() as db:
            db.execute("UPDATE chats SET title=? WHERE id=? AND title='New chat'",(text[:55],cid))
            db.execute('INSERT INTO messages(chat,role,content) VALUES(?,?,?)',(cid,'user',text))
            return db.execute("INSERT INTO messages(chat,role,content,state) VALUES(?,'assistant','','streaming')",(cid,)).lastrowid
    def finish(self,mid,text,thinking,state):
        with self.connect() as db:db.execute('UPDATE messages SET content=?,thinking=?,state=? WHERE id=?',(text,thinking,state,mid))
    @staticmethod
    def extras(settings, chat):
        """The user's own words about themselves and how to answer, then the workspace's instructions."""
        parts = []
        if settings.get('about_me'):
            parts.append('About the user (from their settings): ' + settings['about_me'])
        if settings.get('instructions'):
            parts.append("The user's instructions for every answer (follow them unless they ask for something unsafe): "
                         + settings['instructions'])
        if chat and chat['ws_instructions']:
            parts.append(f'Instructions for the workspace "{chat["ws_name"]}": ' + chat['ws_instructions'])
        return ('\n\n' + '\n\n'.join(parts)) if parts else ''
    def instructions(self, cid):
        """extras() for one chat, e.g. for Code mode, which replaces the usual system prompt."""
        with self.connect() as db:
            chat = db.execute('SELECT w.name AS ws_name,w.instructions AS ws_instructions FROM chats c '
                              'LEFT JOIN workspaces w ON w.id=c.workspace WHERE c.id=?',(cid,)).fetchone()
            return self.extras(self._settings(db), chat)
    def context(self, cid, text):
        with self.connect() as db:
            chat = db.execute('SELECT c.thorough,w.name AS ws_name,w.instructions AS ws_instructions FROM chats c '
                              'LEFT JOIN workspaces w ON w.id=c.workspace WHERE c.id=?',(cid,)).fetchone()
            if chat is None:
                raise ValueError('Chat not found.')
            settings = self._settings(db)
            turns = 12 if chat['thorough'] else 6
            rows = db.execute('SELECT role,content,state FROM messages WHERE chat=? ORDER BY id DESC LIMIT ?', (cid, turns*2)).fetchall()
        system = (f"You are {settings['assistant_name']}, a private offline assistant. "
                  f"Address the user as {settings['user_call_name']}. Reply in {settings['language']}. "
                  f"Tone: {settings['tone']}. Say when you do not know. "
                  "Write formulas in plain text with symbols such as √, ², ×, π and ≈, never in LaTeX or with $ signs; "
                  "this chat cannot render LaTeX.") + self.extras(settings, chat)
        budget = 6000 if chat['thorough'] else 3000
        history = []
        for assistant, user in zip(rows[::2], rows[1::2]):
            if assistant['role'] != 'assistant' or user['role'] != 'user' or assistant['state'] != 'complete':
                continue
            size = sum(len(message['content'].encode('utf-8')) for message in (assistant,user))
            if size > budget:
                break
            history.extend(({'role':'assistant','content':assistant['content']}, {'role':'user','content':user['content']}))
            budget -= size
        return [{'role':'system','content':system}, *reversed(history), {'role':'user','content':text}]
