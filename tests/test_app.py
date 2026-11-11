import base64
import io
from email.parser import BytesParser
from email.policy import default
import struct
import zlib
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('studio', ROOT / 'app.py')
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jS9sAAAAASUVORK5CYII=')


def make_png(width,height):
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes([77,105,51])*width)*height))+chunk(b'IEND',b'')

PNG4K = make_png(3840,2160)

class Provider(BaseHTTPRequestHandler):
    mode = 'base64'
    seen = []
    def log_message(self, *_): pass
    def reply(self, code, body):
        self.send_response(code)
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())
    def do_GET(self):
        self.seen.append((self.path, self.headers.get('Authorization'), None))
        if self.path == '/image.png': return self.reply(200, PNG)
        return self.reply(200, {'data':[{'id':'gpt-image-2.5-sunburst'}]})
    def do_POST(self):
        raw = self.rfile.read(int(self.headers['Content-Length']))
        self.__class__.uploads = []
        if self.headers.get('Content-Type','').startswith('multipart/form-data'):
            message=BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
            body={}
            for part in message.iter_parts():
                field=part.get_param('name',header='content-disposition')
                if part.get_filename():
                    self.__class__.uploads.append((field,part.get_filename(),part.get_content_type(),part.get_payload(decode=True)))
                else:
                    body[field]=part.get_payload(decode=True).decode('utf-8')
        else:
            body = json.loads(raw)
        self.seen.append((self.path, self.headers.get('Authorization'), body))
        if self.mode == '502':
            return self.reply(502, {'error':{'message':'Upstream service temporarily unavailable TEST_SECRET'}})
        if self.mode == 'error':
            return self.reply(401, {'error':{'message':'invalid TEST_SECRET'}})
        if self.mode == 'redirect':
            self.send_response(302)
            self.send_header('Location', '/should-not-follow')
            self.end_headers()
            return
        if self.mode == 'empty': return self.reply(200, {'data':[]})
        item = {'b64_json':base64.b64encode(PNG4K if self.mode == '4k' else PNG).decode()}
        if self.mode == 'url': item = {'url':f'http://127.0.0.1:{self.server.server_port}/image.png'}
        items = [item]
        if self.mode == 'partial': items.append({'b64_json':'broken!'})
        return self.reply(200, {'data':items})


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = ThreadingHTTPServer(('127.0.0.1',0), Provider)
        cls.local = ThreadingHTTPServer(('127.0.0.1',0), studio.Handler)
        for server in (cls.provider, cls.local):
            threading.Thread(target=server.serve_forever,daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.provider.server_port}/v1'
        cls.localbase = f'http://127.0.0.1:{cls.local.server_port}'
    @classmethod
    def tearDownClass(cls):
        for server in (cls.provider, cls.local): server.shutdown(); server.server_close()
    def setUp(self):
        Provider.mode = 'base64'; Provider.seen = []; Provider.uploads = []
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(studio,'IMAGE_DIR',Path(self.temp.name))
        self.patch.start()
        self.data = {'base_url':self.base,'api_key':'TEST_SECRET','model':'gpt-image-2.5-sunburst','prompt':'一只猫'}
    def tearDown(self): self.patch.stop(); self.temp.cleanup()
    def post(self, path, token=True, origin=None):
        headers = {'Content-Type':'application/json'}
        if token: headers['X-Studio-Token'] = studio.TOKEN
        if origin: headers['Origin'] = origin
        return urlopen(Request(self.localbase + path,data=json.dumps(self.data).encode(),headers=headers))
    def test_full_generation_and_image_route(self):
        with self.post('/api/generate') as res: result = json.load(res)
        with urlopen(self.localbase + result['images'][0]['url']) as res: self.assertEqual(res.read(), PNG)
        self.assertEqual(Provider.seen[0],('/v1/images/generations','Bearer TEST_SECRET',{'model':'gpt-image-2.5-sunburst','prompt':'一只猫'}))
        self.assertEqual(list(Path(self.temp.name).glob('*.png'))[0].read_bytes(),PNG)
    def test_url_download_does_not_send_api_key(self):
        Provider.mode = 'url'
        self.assertEqual(len(studio.generate(self.data)['images']),1)
        self.assertEqual(Provider.seen[1],('/image.png',None,None))
    def test_partial_results_preserved(self):
        Provider.mode = 'partial'
        result = studio.generate(self.data)
        self.assertEqual(len(result['images']),1)
        self.assertEqual(len(result['warnings']),1)
    def test_api_error_redacts_key(self):
        Provider.mode = 'error'
        with self.assertRaises(studio.UserError) as ctx: studio.generate(self.data)
        self.assertIn('401',str(ctx.exception)); self.assertNotIn('TEST_SECRET',str(ctx.exception))
    def test_redirect_not_followed(self):
        Provider.mode = 'redirect'
        with self.assertRaises(studio.UserError): studio.generate(self.data)
        self.assertEqual(len(Provider.seen),1)
    def test_empty_response(self):
        Provider.mode = 'empty'
        with self.assertRaises(studio.UserError): studio.generate(self.data)
    def test_models(self):
        with self.post('/api/models') as res: result = json.load(res)
        self.assertEqual(result['models'],['gpt-image-2.5-sunburst'])
    def test_local_token_and_origin(self):
        for token,origin in [(False,None),(True,'https://example.org')]:
            with self.assertRaises(HTTPError) as ctx: self.post('/api/generate',token,origin)
            self.assertEqual(ctx.exception.code,403)
        self.assertFalse(Provider.seen)
    def test_path_traversal_and_host(self):
        for path in ['/generated/../app.py','/generated/%2e%2e%5capp.py']:
            with self.assertRaises(HTTPError) as ctx: urlopen(self.localbase + path)
            self.assertEqual(ctx.exception.code,404)
        with self.assertRaises(HTTPError) as ctx: urlopen(Request(self.localbase,headers={'Host':'evil.example'}))
        self.assertEqual(ctx.exception.code,403)
    def test_optional_parameters_and_validation(self):
        self.data.update(size='1024x1024',n='2',quality='high',output_format='png')
        payload = studio.generation_payload(self.data)
        self.assertEqual(payload['n'],2); self.assertEqual(payload['quality'],'high')
        self.data['n']='9'
        with self.assertRaises(studio.UserError): studio.generation_payload(self.data)
        with self.assertRaises(studio.UserError): studio.clean_url('http://remote.example/v1')
        with self.assertRaises(studio.UserError): studio.clean_url(self.base+'/images/generations')


    def test_4k_alias_quality_and_complexity_end_to_end(self):
        Provider.mode='4k'
        self.data.update(model='gpt-image-2.6-sunburst-4k',size='3840x2160',quality='max',complexity='high',n='1')
        with self.post('/api/generate') as response: result=json.load(response)
        image=result['images'][0]
        self.assertEqual((image['width'],image['height']),(3840,2160))
        self.assertEqual((Path(self.temp.name)/image['name']).read_bytes(),PNG4K)
        self.assertFalse(result['warnings'])
        sent=Provider.seen[0][2]
        self.assertEqual(sent['model'],'gpt-image-2.6-sunburst-4k')
        self.assertEqual(sent['size'],'3840x2160')
        self.assertEqual(sent['quality'],'max'); self.assertEqual(sent['complexity'],'high')
        self.assertNotIn('reasoning',sent)
        self.assertNotIn('prompt',result['parameters'])

    def test_gateway_error_has_actionable_detail_and_no_retry(self):
        Provider.mode='502'
        self.data.update(size='3840x2160',model='gpt-image-2.6-sunburst-4k')
        with self.assertRaises(HTTPError) as ctx: self.post('/api/generate')
        with ctx.exception as response: error=json.load(response)
        self.assertIn('上游调用失败',error['error'])
        self.assertEqual(error['details']['upstream_status'],502)
        self.assertEqual(error['details']['parameters']['size'],'3840x2160')
        self.assertNotIn('TEST_SECRET',json.dumps(error))
        self.assertEqual(len(Provider.seen),1)

    def test_invalid_dimensions_rejected_before_upstream(self):
        for size in ['4K','4096x4096','3840x3840','3841x2160','3840x960','256x256','0x1024','1920x1080']:
            with self.subTest(size=size):
                self.data['size']=size
                with self.assertRaises(studio.UserError): studio.generate(self.data)
        self.assertFalse(Provider.seen)

    def test_valid_size_boundaries(self):
        for size in ['3840x2160','2160x3840','2880x2880','2560x1440','1536x864','1024x640','3072x1024']:
            self.assertEqual(studio.validate_size(size),size)
        self.assertEqual(studio.validate_size('3840×2160'),'3840x2160')
        self.assertEqual(studio.validate_size('auto'),'auto')

    def test_smaller_provider_output_is_not_upscaled(self):
        self.data['size']='3840x2160'
        result=studio.generate(self.data)
        self.assertIn('实际返回 1x1',result['warnings'][0])
        self.assertEqual((Path(self.temp.name)/result['images'][0]['name']).read_bytes(),PNG)

    def test_preview_works_without_key_and_without_upstream(self):
        self.data.pop('api_key')
        self.data.update(size='2160x3840',quality='xhigh',complexity='low')
        with self.post('/api/preview') as response: result=json.load(response)
        self.assertEqual(result['parameters']['size'],'2160x3840')
        self.assertNotIn('prompt',result['parameters'])
        self.assertFalse(Provider.seen)

    def test_quality_complexity_and_compression_validation(self):
        self.data.update(output_format='webp',output_compression='0',quality='xhigh',complexity='medium')
        result=studio.generation_payload(self.data)
        self.assertEqual(result['output_compression'],0)
        self.assertEqual(result['quality'],'xhigh')
        self.assertEqual(result['complexity'],'medium')
        self.data['output_compression']='101'
        with self.assertRaises(studio.UserError): studio.generation_payload(self.data)
        self.data.update(output_compression='',output_format='jpeg',background='transparent')
        with self.assertRaises(studio.UserError): studio.generation_payload(self.data)
        self.data.update(background='',complexity='max')
        with self.assertRaises(studio.UserError): studio.generation_payload(self.data)

    def test_dimensions_across_raster_encodings(self):
        from PIL import Image
        for fmt,options in [('PNG',{}),('JPEG',{}),('JPEG',{'progressive':True}),('WEBP',{}),('WEBP',{'lossless':True}),('WEBP',{'exif':b'Exif\0\0'}),('GIF',{})]:
            with self.subTest(format=fmt,options=options):
                image=Image.new('RGB',(1536,864),(50,120,180)); buffer=io.BytesIO()
                image.save(buffer,format=fmt,**options)
                self.assertEqual(studio.image_dimensions(buffer.getvalue()),(1536,864))
        self.assertIsNone(studio.image_dimensions(b'not an image'))

    def upload(self, raw=PNG):
        return {'name':'图像\"\r\nInjected: no.png','b64_json':base64.b64encode(raw).decode()}

    def test_single_reference_multipart_and_original_bytes(self):
        self.data.update(reference_images=[self.upload()],size='3840x2160',quality='max',complexity='high')
        with self.post('/api/generate') as response: result=json.load(response)
        self.assertEqual(Provider.seen[0][0],'/v1/images/edits')
        self.assertEqual(Provider.seen[0][1],'Bearer TEST_SECRET')
        self.assertEqual(Provider.seen[0][2]['prompt'],'一只猫')
        self.assertEqual(Provider.seen[0][2]['size'],'3840x2160')
        self.assertEqual(Provider.uploads,[('image','reference-1.png','image/png',PNG)])
        self.assertEqual(result['parameters']['endpoint'],'/images/edits')
        self.assertNotIn('b64_json',json.dumps(result['parameters']))
        self.assertNotIn('Injected',json.dumps(result))

    def test_multiple_references_order_and_mime(self):
        from PIL import Image
        buffer=io.BytesIO(); Image.new('RGB',(32,16)).save(buffer,format='JPEG')
        jpeg=buffer.getvalue()
        self.data['reference_images']=[self.upload(),self.upload(jpeg)]
        studio.generate(self.data)
        self.assertEqual(Provider.uploads,[('image[]','reference-1.png','image/png',PNG),('image[]','reference-2.jpg','image/jpeg',jpeg)])
        self.assertEqual(Provider.seen[0][0],'/v1/images/edits')

    def test_empty_reference_list_uses_generation(self):
        self.data['reference_images']=[]
        studio.generate(self.data)
        self.assertEqual(Provider.seen[0][0],'/v1/images/generations')
        self.assertNotIn('reference_images',Provider.seen[0][2])

    def test_reference_preview_is_local_and_private(self):
        self.data.pop('api_key')
        self.data['reference_images']=[self.upload(),self.upload()]
        with self.post('/api/preview') as response: result=json.load(response)
        self.assertEqual(len(result['parameters']['reference_images']),2)
        self.assertFalse(Provider.seen)
        self.assertNotIn('b64_json',json.dumps(result)); self.assertNotIn('prompt',result['parameters'])

    def test_bad_uploads_rejected_without_upstream(self):
        for images in [[self.upload(b'bad')],[{'b64_json':'!!!'}],[{'b64_json':123}],[self.upload()]*17,{'wrong':'shape'},[self.upload(b'GIF89a'+b'\x01\x00\x01\x00')]]:
            self.data['reference_images']=images
            with self.assertRaises(studio.UserError): studio.generate(self.data)
        self.assertFalse(Provider.seen)

    def test_upload_byte_and_pixel_limits(self):
        self.data['reference_images']=[self.upload()]
        with patch.object(studio,'MAX_REFERENCE',len(PNG)-1):
            with self.assertRaises(studio.UserError): studio.generate(self.data)
        self.data['reference_images']=[self.upload(),self.upload()]
        with patch.object(studio,'MAX_REFERENCE_TOTAL',len(PNG)*2-1):
            with self.assertRaises(studio.UserError): studio.generate(self.data)
        huge=bytearray(PNG); huge[16:24]=struct.pack('>II',10000,10000)
        self.data['reference_images']=[self.upload(bytes(huge))]
        with self.assertRaises(studio.UserError): studio.generate(self.data)
        self.assertFalse(Provider.seen)

    def test_edit_502_does_not_fallback_or_retry(self):
        self.data['reference_images']=[self.upload()]; Provider.mode='502'
        with self.assertRaises(studio.UserError) as ctx: studio.generate(self.data)
        self.assertEqual(ctx.exception.details['parameters']['endpoint'],'/images/edits')
        self.assertEqual(len(Provider.seen),1)
        self.assertNotIn('b64_json',json.dumps(ctx.exception.details))

    def test_reference_js_is_served_and_blob_previews_allowed(self):
        with urlopen(self.localbase+'/references.js') as response:
            self.assertIn(b'referenceUploads',response.read())
            self.assertIn('javascript',response.headers['Content-Type'])
            self.assertIn('blob:',response.headers['Content-Security-Policy'])

    def test_request_size_guard(self):
        with patch.object(studio,'MAX_LOCAL_REQUEST',100):
            with self.assertRaises(HTTPError) as ctx: self.post('/api/generate')
            self.assertEqual(ctx.exception.code,413)
        self.assertFalse(Provider.seen)

if __name__ == '__main__': unittest.main(verbosity=2)
