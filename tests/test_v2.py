import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from contextlib import ExitStack

from PIL import Image
import server
import v2_local


class IsolatedStudio(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for key, value in {'DATA':self.root, 'UPLOADS':self.root/'uploads', 'DB_PATH':self.root/'app.sqlite3', 'SETTINGS_PATH':self.root/'settings.json', 'SECRETS_PATH':self.root/'secrets.json', 'ETSY_OAUTH_PATH':self.root/'etsy_oauth.json'}.items():
            self.stack.enter_context(patch.object(server,key,value))
        self.stack.enter_context(patch.dict(server.DEFAULT_SETTINGS, {'selection_mockup_root': str(self.root/'templates'/'Selections')}))
        server.init_db()

    def test_clean_start_and_private_secrets(self):
        with patch.dict(os.environ, {'ETSY_KEYSTRING':'legacy-do-not-import'}):
            self.assertNotIn('etsy_keystring', server.get_settings()['_secrets'])
        status=v2_local.status(server)
        self.assertFalse(status['etsy_connected'])
        self.assertEqual(status['mode'],'dry_run')
        self.assertIn(':8766/', status['callback_url'])
        server.save_settings({'etsy_keystring':'my-key','etsy_shared_secret':'my-secret'})
        self.assertTrue(server.public_settings()['secret_status']['etsy_keystring'])
        self.assertNotIn('my-secret', json.dumps(server.public_settings()))

    def test_changing_keys_clears_old_shop_token(self):
        server.save_settings({'etsy_keystring':'first','etsy_shared_secret':'secret'})
        server.save_secret_updates({'etsy_access_token':'old-token','etsy_shop_id':'123','etsy_shipping_profile_id':'456'})
        server.save_settings({'workspace_name':'A different name'})
        self.assertEqual(server.get_settings()['_secrets']['etsy_access_token'],'old-token')
        server.save_settings({'etsy_keystring':'second'})
        secrets=server.get_settings()['_secrets']
        self.assertNotIn('etsy_access_token',secrets)
        self.assertNotIn('etsy_shop_id',secrets)

    def test_reauthorization_rediscover_shop_and_consumes_state(self):
        server.save_settings({'etsy_keystring':'key','etsy_shared_secret':'secret'})
        server.save_secret_updates({'etsy_shop_id':'old-shop','etsy_shipping_profile_id':'old-profile'})
        server.start_etsy_oauth()
        state=server.read_json_file(server.ETSY_OAUTH_PATH,{})['state']
        with patch.object(server,'request_form_json',return_value={'access_token':'new-token','refresh_token':'refresh'}), patch.object(server,'discover_etsy_shop_settings') as discover:
            server.exchange_etsy_oauth_code('test-code',state)
        self.assertNotIn('etsy_shop_id',discover.call_args.args[0]['_secrets'])
        self.assertNotIn('etsy_shipping_profile_id',server.get_settings()['_secrets'])
        with self.assertRaises(ValueError):
            server.exchange_etsy_oauth_code('test-code',state)

    def test_collection_copies_arbitrary_names_and_video(self):
        source=self.root/'my-own-template.psd'; source.write_bytes(b'8BPS-test-fixture')
        video=self.root/'my-video.mp4'; video.write_bytes(b'fixture-video')
        result=v2_local.create_collection(server,{'name':'Arkadaşımın koleksiyonu','mockups':[str(source)],'video':str(video)})
        self.assertEqual(result['mockup_count'],1)
        info=server.selection_template_info(result['name'])
        self.assertTrue(info['ready'])
        self.assertEqual(Path(info['static_psds'][0]).read_bytes(), source.read_bytes())
        self.assertNotEqual(Path(info['static_psds'][0]),source)
        self.assertEqual(len(info['ready_videos']),1)
        with self.assertRaises(ValueError):
            v2_local.create_collection(server,{'name':result['name'],'mockups':[str(source)]})

    def test_collection_rejects_traversal_and_invalid_psd(self):
        for name in ['../escape','CON','NUL.txt','bad/name','test.']:
            with self.assertRaises(ValueError):
                v2_local.create_collection(server,{'name':name,'mockups':['fake.psd']})
        bad=self.root/'wrong.psd';bad.write_bytes(b'not-photoshop')
        with self.assertRaisesRegex(ValueError,'Photoshop'):
            v2_local.create_collection(server,{'name':'test','mockups':[str(bad)]})
        self.assertFalse((server.selection_mockup_root()/'test').exists())

    def test_generic_cover_accepts_non_legacy_name_and_ratio(self):
        output=self.root/'my-mockup.jpg'; Image.new('RGB',(500,700),'blue').save(output)
        server.validate_primary_thumbnail_image(output)
        with patch.object(server,'add_asset') as add:
            server.copy_external_assets('local',{'mockups':[output],'videos':[]})
        self.assertEqual(add.call_args.kwargs['role'],'primary_thumbnail')
        self.assertEqual(server.validate_static_listing_sources(), [])

    def test_new_product_uses_local_data_only(self):
        image=io.BytesIO();Image.new('RGB',(80,100),'orange').save(image,format='PNG')
        payload={'name':'Yerel deneme','selection_name':'İlk koleksiyonum','image_file':{'filename':'poster.png','data_url':'data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()}}
        product=server.create_product(payload)['products'][0]
        self.assertTrue(Path(product['source_image_path']).is_relative_to(self.root))
        self.assertFalse(product.get('listing_id'))

    def test_arbitrary_cover_manifest_with_no_seller_static_images(self):
        image=io.BytesIO();Image.new('RGB',(100,150),'red').save(image,format='PNG')
        product=server.create_product({'selection_name':'İlk koleksiyonum','image_file':{'filename':'original.png','data_url':'data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()}})['products'][0]
        job_root=server.product_upload_dir(product['id'])/'preview-job';job_root.mkdir()
        output=job_root/'custom-room.jpg';Image.new('RGB',(500,700),'blue').save(output)
        preview=server.build_existing_media_preview(product['id'],job_root,[str(output)],[],product['source_image_path'])
        self.assertEqual(preview['images'][0]['role'],'primary_thumbnail')
        server.validate_existing_media_preview(product['id'],preview,job_root)

    def test_margin_and_markup_differ(self):
        self.assertEqual(server.sale_from_cost(60,40,'margin'),100)
        self.assertEqual(server.sale_from_cost(60,40,'markup'),84)
        with self.assertRaises(ValueError):server.sale_from_cost(60,100,'margin')

    def test_disconnect_resets_mode_and_preserves_products(self):
        server.save_settings({'etsy_keystring':'k','etsy_shared_secret':'s','etsy_mode':'draft'})
        v2_local.action(server,'/api/v2/disconnect',{'confirmation':'disconnect'})
        self.assertFalse(server.public_settings()['secret_status']['etsy_keystring'])
        self.assertEqual(server.get_settings()['etsy_mode'],'dry_run')
        self.assertTrue(server.DB_PATH.exists())

    def test_api_blocks_foreign_origin_and_bad_host(self):
        http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        port=http.server_port
        self.stack.enter_context(patch.object(server,'APP_PORT',port))
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        self.addCleanup(http.server_close);self.addCleanup(http.shutdown)
        url=f'http://127.0.0.1:{port}'
        with urllib.request.urlopen(url+'/api/health') as response:
            self.assertEqual(json.load(response)['app'],'etsy-ekosistem-v2')
        for headers in [{'Origin':'https://other-site.example'}, {'Host':'other-site.example'}]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(url+'/api/v2/status',headers=headers))
            self.assertEqual(error.exception.code,403)

    def test_no_personal_data_in_distribution_allowlist(self):
        spec=importlib.util.spec_from_file_location('package_release',Path(server.ROOT)/'tools'/'package_release.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for directory in module.DIRS:
            self.assertNotIn(directory,{'data','logs','validation','templates'})
        self.assertNotIn('original-hashes.json',module.FILES)

if __name__=='__main__':unittest.main()
