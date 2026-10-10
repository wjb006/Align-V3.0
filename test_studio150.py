import base64,io,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
import asset_studio,transport_places
from migration_runner import migrate

class Studio150Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'owner.sqlite3';sqlite3.connect(self.db).close();migrate(self.db)
  self.c=sqlite3.connect(self.db);self.c.row_factory=sqlite3.Row;self.c.execute('PRAGMA foreign_keys=ON')
 def tearDown(self): self.c.close();self.tmp.cleanup()
 def body(self):
  out=io.BytesIO();Image.new('RGBA',(300,150),'blue').save(out,format='PNG')
  return {'name':'Bus icon','image':base64.b64encode(out.getvalue()).decode(),'crop':'fit','category':self.c.execute("SELECT category_id FROM asset_categories WHERE category_group='travel' AND category_key='bus'").fetchone()[0]}
 def test_image_lifecycle_and_category_default(self):
  with self.c: ident=asset_studio.create(self.c,self.db,self.body())['asset_id']
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM asset_variants').fetchone()[0],4)
  with self.c: asset_studio.change(self.c,{'id':ident,'version':1,'action':'activate'})
  with self.c: asset_studio.change(self.c,{'id':ident,'version':2,'action':'default'})
  self.assertEqual(self.c.execute('SELECT default_asset_id FROM asset_categories WHERE default_asset_id=?',(ident,)).fetchone()[0],ident)
  with self.c: asset_studio.change(self.c,{'id':ident,'version':3,'action':'deactivate'})
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM asset_categories WHERE default_asset_id IS NOT NULL').fetchone()[0],0)
 def test_bad_image_and_invalid_category_leave_no_asset(self):
  for values in ({'name':'bad','image':base64.b64encode(b'<svg/>').decode()},dict(self.body(),category=99999)):
   with self.assertRaises((ValueError,OSError)):
    with self.c: asset_studio.create(self.c,self.db,values)
   self.assertEqual(self.c.execute('SELECT COUNT(*) FROM assets').fetchone()[0],0)
 def test_stale_edit_rejected(self):
  with self.c: ident=asset_studio.create(self.c,self.db,self.body())['asset_id']
  with self.assertRaises(ValueError): asset_studio.change(self.c,{'id':ident,'version':999,'action':'rename','name':'x'})
 def test_account_image_directories_differ(self):
  self.assertNotEqual(asset_studio.image_root(self.db),asset_studio.image_root(self.db.with_name('tester.sqlite3')))
 def test_non_owner_rejected_before_database(self):
  h=Mock();h.path='/api/asset-studio';h.require_beta_user.return_value=True;h.require_admin.return_value=False
  app=Mock();app.BETA_MODE=True
  self.assertTrue(asset_studio.handle(h,app,'GET'));app.db_connection.assert_not_called()
 def test_local_stops_no_external_request(self):
  with patch('transport_places.request_json') as request:
   result=transport_places.lookup({'query':'Lime Street'})
   self.assertTrue(result['places']);request.assert_not_called()
 def test_postcode_requires_explicit_consent(self):
  with patch('transport_places.request_json') as request:
   with self.assertRaises(ValueError): transport_places.lookup({'query':'L1 8JQ'})
   request.assert_not_called()
if __name__=='__main__':unittest.main()
