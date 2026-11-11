import unittest,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.storage import Store,DEFAULTS
class StorageTests(unittest.TestCase):
    def setUp(self):self.box=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.test-runs');self.s=Store(self.box.name)
    def tearDown(self):self.box.cleanup()
    def chat(self):return self.s.mutate({'action':'chat','model':'qwen3-it:4b'})['id']
    def test_restart_history_and_settings(self):
        c=self.chat();m=self.s.begin(c,'Remember this');self.s.finish(m,'Saved answer','reasoning','complete')
        settings={**DEFAULTS,'user_call_name':'Alex','theme':'light'};self.s.mutate({'action':'settings','settings':settings})
        again=Store(self.box.name);self.assertEqual(again.state()['settings'],settings);self.assertEqual(again.chat(c)['messages'][1]['content'],'Saved answer')
        self.assertEqual(again.context(c,'Follow up')[-2]['content'],'Saved answer')
    def test_crash_recovery_marks_partial(self):
        c=self.chat();self.s.begin(c,'Hello');again=Store(self.box.name);self.assertEqual(again.chat(c)['messages'][-1]['state'],'interrupted')
    def test_workspace_isolation_and_delete(self):
        w=self.s.mutate({'action':'workspace','name':'Research'})['id'];c=self.s.mutate({'action':'chat','workspace':w})['id'];other=self.chat();self.s.begin(c,'x');self.s.mutate({'action':'delete','id':c})
        with self.assertRaises(ValueError):self.s.chat(c)
        self.assertEqual(self.s.chat(other)['workspace'],'default')
    def test_invalid_settings_rejected(self):
        with self.assertRaises(ValueError):self.s.mutate({'action':'settings','settings':{**DEFAULTS,'theme':'evil'}})
        self.assertEqual(self.s.state()['settings'],DEFAULTS)
    def test_sql_text_is_data(self):
        name="'; DROP TABLE chats; --";self.s.mutate({'action':'workspace','name':name});self.assertEqual(self.s.state()['workspaces'][-1]['name'],name);self.chat()
    def test_interrupted_turn_is_excluded_as_a_pair(self):
        c=self.chat(); first=self.s.begin(c,'Earlier question');self.s.finish(first,'Earlier reply','','complete')
        failed=self.s.begin(c,'Interrupted question');self.s.finish(failed,'Partial answer','','interrupted')
        history=self.s.context(c,'Retry')[1:]
        self.assertEqual([m['content'] for m in history],['Earlier question','Earlier reply','Retry'])
    def test_context_bounded(self):
        c=self.chat()
        for i in range(8):m=self.s.begin(c,'x'*500);self.s.finish(m,'a'*500,'','complete')
        context=self.s.context(c,'next');self.assertLessEqual(sum(len(m['content'].encode()) for m in context[1:-1]),3000)
if __name__=='__main__':unittest.main(verbosity=2)
