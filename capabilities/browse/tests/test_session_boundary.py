import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from browse_session import SessionManager,SessionError

class SessionBoundaryTests(unittest.TestCase):
 def test_traversal_rejected_before_any_session_access(self):
  with tempfile.TemporaryDirectory() as tmp:
   manager=SessionManager(Path(tmp)/'sessions')
   for sid in ('../outside','/tmp/outside','..','a/b','a\\b'):
    for call in (lambda:manager.create(session_id=sid),lambda:manager.load(sid),lambda:manager.get(sid),lambda:manager.destroy(sid)):
     with self.assertRaises(SessionError):call()
   self.assertFalse((Path(tmp)/'outside').exists())
 def test_symlink_directory_and_state_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);manager=SessionManager(root/'sessions');outside=root/'other';outside.mkdir()
   (manager.root/'escape').symlink_to(outside,target_is_directory=True)
   with self.assertRaises(SessionError):manager.create(session_id='escape')
   session=manager.create(session_id='safe',persistent=True)
   (manager.root/'safe'/'state.json').symlink_to(outside/'target.json')
   with self.assertRaises(SessionError):manager.save(session)
   self.assertFalse((outside/'target.json').exists())

if __name__=='__main__':unittest.main()
