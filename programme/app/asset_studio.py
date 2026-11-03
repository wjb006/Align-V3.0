"""Owner Asset Studio. Images are decoded and re-encoded; no user paths served."""
import base64,hashlib,io,json,os,re,sqlite3,uuid,warnings
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image,ImageOps,UnidentifiedImageError
Image.MAX_IMAGE_PIXELS=20000000

def image_root(database):
    db=Path(database).resolve()
    return db.parent/(db.stem+'_assets')

def object_storage_configured():
    return all(os.environ.get(key, '').strip() for key in (
        'AWS_ENDPOINT_URL_S3', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'ALIGN_ASSET_BUCKET'
    ))

@lru_cache(maxsize=1)
def _s3_client():
    if not object_storage_configured(): raise OSError('Persistent image storage is not configured')
    import boto3
    from botocore.config import Config
    return boto3.client(
        's3', endpoint_url=os.environ['AWS_ENDPOINT_URL_S3'].strip(),
        region_name=os.environ.get('AWS_REGION', 'auto').strip() or 'auto',
        aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'].strip(),
        aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'].strip(),
        config=Config(signature_version='s3v4', s3={'addressing_style': 'path'}),
    )

def _store_variant(database, filename, payload):
    if object_storage_configured():
        try:
            _s3_client().put_object(Bucket=os.environ['ALIGN_ASSET_BUCKET'].strip(), Key=filename,
                                    Body=payload, ContentType='image/png', CacheControl='private, max-age=31536000')
        except Exception as exc: raise OSError('Persistent image upload failed') from exc
    else:
        root=image_root(database); root.mkdir(exist_ok=True); (root/filename).write_bytes(payload)

def _load_variant(database, filename):
    if object_storage_configured():
        try:
            response=_s3_client().get_object(Bucket=os.environ['ALIGN_ASSET_BUCKET'].strip(), Key=filename)
            return response['Body'].read()
        except Exception as exc: raise OSError('Persistent image could not be read') from exc
    root=image_root(database).resolve(); file=(root/filename).resolve()
    if file.parent!=root: raise ValueError('Invalid image path')
    return file.read_bytes()

def listing(c):
    return {'assets':[dict(r) for r in c.execute('SELECT asset_id,display_name,asset_type,category_id,status,version FROM assets ORDER BY asset_id DESC LIMIT 500')], 'categories':[dict(r) for r in c.execute('SELECT category_id,display_name,category_group,default_asset_id FROM asset_categories ORDER BY category_group,sort_order,display_name')]}

def create(c,database,body):
    name=str(body.get('name','')).strip()
    if not 1<=len(name)<=60: raise ValueError('Use an image name of 1–60 characters')
    encoded=body.get('image','')
    if not isinstance(encoded,str) or len(encoded)>850000: raise ValueError('Image too large; choose a smaller image')
    raw=base64.b64decode(encoded,validate=True)
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as original:
            if original.format not in ('PNG','JPEG','WEBP'): raise ValueError('Choose PNG, JPEG or WebP')
            im=ImageOps.exif_transpose(original).convert('RGBA')
            im.thumbnail((1024,1024))
    if body.get('crop')=='square': im=ImageOps.fit(im,(512,512))
    elif body.get('crop','fit')!='fit': raise ValueError('Choose fit or square crop')
    token=uuid.uuid4().hex
    category=int(body['category']) if body.get('category') else None
    group=c.execute('SELECT category_group FROM asset_categories WHERE category_id=?',(category,)).fetchone() if category else None
    if category and not group: raise ValueError('Choose an existing category')
    kind=group[0] if group and group[0] in ('place','workplace','event_type','travel','section') else 'general_image'
    # Strip EXIF and other source metadata; image content never enters SQLite.
    out=io.BytesIO(); im.save(out,format='PNG'); data=out.getvalue()
    ident=c.execute("""INSERT INTO assets(asset_key,display_name,asset_type,category_id,original_filename,original_mime_type,original_width,original_height,original_file_size,content_sha256,created_by,updated_by,created_at,updated_at) VALUES(?,?,?,?,?,'image/png',?,?,?,?, 'owner','owner',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",(token,name,kind,category,token+'.png',im.width,im.height,len(data),hashlib.sha256(data).hexdigest())).lastrowid
    for variant,size in [('original',1024),('small',64),('medium',192),('large',512)]:
        image=im.copy(); image.thumbnail((size,size)); buf=io.BytesIO(); image.save(buf,format='PNG'); payload=buf.getvalue()
        filename=token+'_'+variant+'.png'; _store_variant(database,filename,payload)
        c.execute("INSERT INTO asset_variants(asset_id,variant_type,width,height,mime_type,stored_filename,storage_path,file_size,content_sha256,created_at) VALUES(?,?,?,?, 'image/png',?,?,?,?,CURRENT_TIMESTAMP)",(ident,variant,image.width,image.height,filename,filename,len(payload),hashlib.sha256(payload).hexdigest()))
    for area in ('today','planner','event_editor','workplace_selector','saved_places','sections','travel'):
        c.execute('INSERT INTO asset_usage_rules VALUES(?,?,1)',(ident,area))
    c.execute("INSERT INTO asset_audit_log(asset_id,action,actor_user_id,details_json,created_at) VALUES(?,'created','owner','{}',CURRENT_TIMESTAMP)",(ident,))
    return {'asset_id':ident}

def change(c,body):
    ident=int(body['id']); version=int(body['version'])
    row=c.execute('SELECT version,category_id FROM assets WHERE asset_id=?',(ident,)).fetchone()
    if not row or row[0]!=version: raise ValueError('Image changed; reload the studio before editing')
    action=body.get('action')
    if action=='rename':
        name=str(body.get('name','')).strip()
        if not 1<=len(name)<=60: raise ValueError('Use a name of 1–60 characters')
        c.execute('UPDATE assets SET display_name=? WHERE asset_id=?',(name,ident))
    elif action=='activate': c.execute("UPDATE assets SET active=1,status='active' WHERE asset_id=?",(ident,))
    elif action=='deactivate':
        c.execute('UPDATE asset_categories SET default_asset_id=NULL WHERE default_asset_id=?',(ident,))
        c.execute("UPDATE assets SET active=0,status='inactive' WHERE asset_id=?",(ident,))
    elif action=='default':
        if not row[1]: raise ValueError('This image has no category')
        c.execute('UPDATE asset_categories SET default_asset_id=? WHERE category_id=?',(ident,row[1]))
    else: raise ValueError('Unknown action')
    c.execute('UPDATE assets SET version=version+1,updated_at=CURRENT_TIMESTAMP WHERE asset_id=?',(ident,))
    c.execute("INSERT INTO asset_audit_log(asset_id,action,actor_user_id,details_json,created_at) VALUES(?,'updated','owner',?,CURRENT_TIMESTAMP)",(ident,json.dumps({'action':action})))
    return {'saved':True}

def handle(h,app,method):
    path=urlparse(h.path).path
    if not path.startswith('/api/asset-studio'): return False
    try:
        body=h.read_json() if method=='POST' else {}
        if app.BETA_MODE and not h.require_beta_user(): return True
        if not h.require_admin(): return True
        if method=='POST':
            if app.BETA_MODE:
                if not h.beta_same_origin(): return True
            elif h.headers.get('Origin') not in (None,'http://'+h.headers.get('Host',''),'https://'+h.headers.get('Host','')):
                h.send_json(403,{'error':'Use the current Align site'}); return True
        with app.db_connection() as c:
            if path=='/api/asset-studio' and method=='GET': result=listing(c)
            elif path=='/api/asset-studio/upload' and method=='POST':
                if app.BETA_MODE and not object_storage_configured():
                    h.send_json(503,{'error':'Persistent image storage is not configured. Ask the Align owner to finish storage setup.'}); return True
                result=create(c,app.current_database(),body)
            elif path=='/api/asset-studio/change' and method=='POST': result=change(c,body)
            elif method=='GET' and re.fullmatch(r'/api/asset-studio/image/\d+',path):
                row=c.execute("SELECT storage_path FROM asset_variants WHERE asset_id=? AND variant_type='medium'",(int(path.rsplit('/',1)[1]),)).fetchone()
                if not row: h.send_json(404,{'error':'Image not found'}); return True
                payload=_load_variant(app.current_database(),row[0]); h.send_response(200); h.send_header('Content-Type','image/png'); h.send_header('Content-Length',str(len(payload))); h.send_header('Cache-Control','private, no-store'); h.send_header('X-Content-Type-Options','nosniff'); h.end_headers(); h.wfile.write(payload); return True
            else: h.send_json(404,{'error':'Not found'}); return True
        h.send_json(200,result)
    except (ValueError,TypeError,KeyError,sqlite3.IntegrityError,UnidentifiedImageError,Image.DecompressionBombError,Image.DecompressionBombWarning): h.send_json(400,{'error':'Check the image and fields. Activate an image before making it a category default.'})
    except OSError: h.send_json(503,{'error':'Image storage is unavailable'})
    return True
