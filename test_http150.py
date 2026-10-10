import base64,io,json,socket,sqlite3,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import app
import transport_service

class Http150Tests(unittest.TestCase):
 def test_malformed_request_error_does_not_crash_handler(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(app,'DATABASE',Path(folder)/'test.sqlite3'),patch.object(app,'BETA_MODE',False),patch.object(app,'ADMIN_PASSWORD',''):
   app.initialise_database()
   server=app.AlignServer(('127.0.0.1',0),app.AlignHandler)
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   try:
    with socket.create_connection(('127.0.0.1',server.server_port),timeout=5) as client:
     client.sendall(b'not-an-http-request\r\n\r\n')
     response=client.recv(4096)
    self.assertIn(b'400',response)
    with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/health',timeout=5) as healthy:
     self.assertEqual(healthy.status,200)
   finally:server.shutdown();server.server_close();thread.join()

 def test_transport_configuration_and_route(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(app,'DATABASE',Path(folder)/'test.sqlite3'),patch.object(app,'BETA_MODE',False),patch.object(app,'ADMIN_PASSWORD',''):
   app.initialise_database()
   server=app.AlignServer(('127.0.0.1',0),app.AlignHandler)
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   base='http://127.0.0.1:'+str(server.server_port)
   def request(path,body=None):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    try:
     with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.loads(r.read())
    except urllib.error.HTTPError as error:
     return error.code,json.loads(error.read())
   try:
    with patch.dict(transport_service.os.environ, {'ALIGN_TRANSPORT_ENABLED':'1','ALIGN_OTP_URL':'http://127.0.0.1:8080/otp/gtfs/v1'}, clear=True):
     status,result=request('/api/transport/status')
     self.assertEqual(status,200)
     self.assertTrue(result['enabled'])
     self.assertTrue(result['routing_configured'])
    with patch.dict(transport_service.os.environ, {'ALIGN_TRANSPORT_ENABLED':'0'}, clear=True):
     status,result=request('/api/transport/journeys',{'event_key':'shift:1'})
     self.assertEqual(status,404)
     self.assertEqual(result['error'],'Transport is disabled')
   finally:server.shutdown();server.server_close();thread.join()

 def test_routes_and_unauthenticated_owner_guard(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(app,'DATABASE',Path(folder)/'test.sqlite3'),patch.object(app,'BETA_MODE',False),patch.object(app,'ADMIN_PASSWORD',''):
   app.initialise_database()
   server=app.AlignServer(('127.0.0.1',0),app.AlignHandler)
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   base='http://127.0.0.1:'+str(server.server_port)
   def request(path,body=None):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=5) as r:return r.status,r.read()
   try:
    status,payload=request('/api/health')
    self.assertEqual(status,200)
    health=json.loads(payload)
    self.assertEqual(health['mode'],'normal')
    self.assertEqual(health['version']['build'],app.BUILD_VERSION)
    self.assertTrue(health['database']['available'])
    self.assertTrue(health['migrations']['available'])
    self.assertEqual(request('/travel-assets.js')[0],200)
    status,payload=request('/api/asset-studio');self.assertEqual(status,200);self.assertIn('categories',json.loads(payload))
    out=io.BytesIO();Image.new('RGB',(50,30),'blue').save(out,format='PNG')
    status,payload=request('/api/asset-studio/upload',{'name':'Test','image':base64.b64encode(out.getvalue()).decode()});self.assertEqual(status,200)
    ident=json.loads(payload)['asset_id'];self.assertEqual(request('/api/asset-studio/image/'+str(ident))[0],200)
    with patch.object(app,'ADMIN_PASSWORD','guard'):
     with self.assertRaises(urllib.error.HTTPError) as error: request('/api/asset-studio')
     self.assertEqual(error.exception.code,403)
   finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
