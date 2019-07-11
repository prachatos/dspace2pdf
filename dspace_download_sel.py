import requests
import os
import re
import configparser
import urllib.request
from urllib.error import HTTPError

from PyPDF2 import PdfFileMerger, PdfFileReader
from fpdf import FPDF
import PyPDF2
from lxml import html
import time
import _helpers


class EAPBookFetch:

    EAP_BASE_URL = 'http://dspace.wbpublibnet.gov.in:8080'
    EAP_INDEX_URL = '/jspui/handle/'
    EAP_CONFIG_FILENAME = 'dsp_conf.ini'
    EAP_FILENAME = 'default.jpg'
    DEFAULT_HEIGHT = 1200
    DEFAULT_WIDTH = 1200 * 0.8
    JPEG_PATH = 'jpgs'
    PDF_PATH = 'pdfs'
    API_BASE_URL = 'https://commons.wikimedia.org/w/api.php'
    CHUNK_SIZE = 1000000

    @staticmethod
    def join_url(*args):
        joined_url = ''
        for arg in args:
            joined_url = joined_url + arg + '/'
        return joined_url

    @staticmethod
    def set_rotate(angle):
        if angle == 90 or angle == 180 or angle == 270:
            return angle
        else:
            return 0

    def get_url_for_page(self):
        page = requests.get(self.url)
        links = html.fromstring(page.content).findall('.//a')
        urls = []
        for x in links:
            if "/jspui/bitstream" in x.get('href') and self.EAP_BASE_URL + x.get('href') not in urls:
                urls.append(self.EAP_BASE_URL + x.get('href'))
        return urls

    def download_jpg(self):
        urls = self.get_url_for_page()
        #print(urls, len(urls))
        count = 0
        filenames = []
        if not os.path.exists(self.PDF_PATH):
            os.makedirs(self.PDF_PATH)
        for url in urls:
            count += 1

            print('Downloading part', count)
            title = os.path.join(self.PDF_PATH, self.ds_fn + '_' + str(count) + '.pdf')
            # nexttitle = os.path.join(self.PDF_PATH, self.ds_fn + '_' + str(count + 1) + '.pdf')

            if os.path.exists(title):
                os.remove(title)

            urllib.request.urlretrieve(url, title)
            filenames.append(title)
        print('Merging', count, 'files')
        if os.path.exists(os.path.join(self.PDF_PATH, self.ds_fn + '.pdf')):
            os.remove(os.path.join(self.PDF_PATH, self.ds_fn + '.pdf'))
        open(os.path.join(self.PDF_PATH, self.ds_fn + '.pdf'), 'w')

        merger = PdfFileMerger()
        for filename in filenames:
            merger.append(PdfFileReader(open(filename, 'rb')))
        merger.write(os.path.join(self.PDF_PATH, self.ds_fn + '.pdf'))
        for filename in filenames:
            try:
                os.remove(filename)
            except Exception:
                pass
        return self.ds_fn


    def read_config(self):
        config_parser = configparser.ConfigParser()
        config_parser.read(self.EAP_CONFIG_FILENAME, encoding='utf8')
        self.url = self.EAP_BASE_URL + self.EAP_INDEX_URL + config_parser.get('download', 'url')

        try:
            self.username = config_parser.get('wiki', 'username')
            self.password = config_parser.get('wiki', 'pwd')
            if config_parser.has_option('wiki', 'summary'):
                self.summary = config_parser.get('wiki', 'summary')
            self.title = config_parser.get('wiki', 'title')
            self.filename = config_parser.get('wiki', 'filename')
            self.description = config_parser.get('wiki', 'desc')
            self.author = config_parser.get('wiki', 'author')
            self.license = config_parser.get('wiki', 'license')
            self.date = config_parser.get('wiki', 'date')
            self.API_BASE_URL = 'https://' + config_parser.get('lang') + '.' + config_parser.get('proj') + '.org/w/api.php'
        except Exception:
            pass
        if not self.filename:
            self.ds_fn = config_parser.get('download', 'url').replace('/', '_')
        else:
            self.ds_fn = self.filename


    def get_token(self):
        session = requests.Session()
        login_t = session.get(self.API_BASE_URL, params={
            'format': 'json',
            'action': 'query',
            'meta': 'tokens',
            'type': 'login',
        })
        login_t.raise_for_status()
        login = session.post(self.API_BASE_URL, data={
            'format': 'json',
            'action': 'login',
            'lgname': self.username,
            'lgpassword': self.password,
            'lgtoken': login_t.json()['query']['tokens']['logintoken'],
        })
        if login.json()['login']['result'] != 'Success':
            raise RuntimeError(login.json()['login']['reason'])

        # get edit token
        tokens = session.get(self.API_BASE_URL, params={
            'format': 'json',
            'action': 'query',
            'meta': 'tokens',
        })
        return session, tokens.json()['query']['tokens']['csrftoken']

    def upload_file(self, session, filename):
        can_go = True
        filename = os.path.join(self.PDF_PATH, filename + '.pdf')
        filekey = ''
        filesize = os.path.getsize(filename)
        print(self.token)
        offset = 0
        i = 1
        page_content = "=={{int:filedesc}}==\n" + \
                       "{{Book\n" + \
                       "| Author       = " + self.author + "\n" + \
                       "| Title        = " + self.title + "\n" + \
                       "| Date         = " + self.date + "\n" + \
                       "| Language     = {{language|bn}}\n" + \
                       "| Wikisource   = s:bn:নির্ঘণ্ট:{{PAGENAME}}\n" + \
                       "| Description  = " + self.description + "\n" + \
                       "| Source       =  {{Endangered Archives Programme|url=" + self.url + \
                       "}}{{Institution:British Library}}\n" + \
                       "| Image        =  {{PAGENAME}}\n" + \
                       "}}\n" + \
                       "=={{int:license-header}}==\n" + self.license + "\n" + \
                       "[[Category:Uploaded with dspace2pdf]]\n" + \
                       "[[Category:PDF-files in Bengali]]"
        with open(filename, 'rb') as f:
            while can_go:
                chunk = f.read(self.CHUNK_SIZE)
                if offset == 0:
                    upload = session.post(self.API_BASE_URL, data={
                        'format': 'json',
                        'action': 'upload',
                        'filename': self.filename + '.pdf',
                        'filesize': filesize,
                        'offset': offset,
                        'chunk': chunk,
                        'token': self.token
                    }, files={'chunk': chunk,
                              'filename': self.filename + '.pdf'})
                    print('Uploaded ' + str(i) + ' MB...')
                    i = i + 1
                    try:
                        filekey = upload.json()['upload']['filekey']
                    except (KeyError, NameError):
                        print(upload.json())
                        raise RuntimeError('Upload failed - try manually!')
                else:
                    upload = session.post(self.API_BASE_URL, data={
                        'format': 'json',
                        'action': 'upload',
                        'filename': self.filename + '.pdf',
                        'filesize': filesize,
                        'filekey': filekey,
                        'offset': offset,
                        'chunk': chunk,
                        'token': self.token
                    }, files={'chunk': chunk,
                              'filename': self.filename + '.pdf'})
                    print('Uploaded ' + str(i) + ' MB...')
                    i = i + 1
                    try:
                        filekey = upload.json()['upload']['filekey']
                    except (KeyError, NameError):
                        print(upload.json())
                        raise RuntimeError('Upload failed - try manually!')
                if upload.json()['upload']['result'] == 'Success':
                    done = session.post(self.API_BASE_URL, data={
                        'format': 'json',
                        'action': 'upload',
                        'filename': self.filename + '.pdf',
                        'filekey': filekey,
                        'comment': self.summary,
                        'token': self.token,
                        'text': page_content
                    }, files={'filename': self.filename + '.pdf'})
                    if 'error' in done.json():
                        raise RuntimeError('Could not complete upload. You probably got caught by an abuse filter')
                    else:
                        print('Done!')
                    break
                elif upload.json()['upload']['result'] == 'Continue':
                    try:
                        offset = upload.json()['upload']['offset']
                    except (KeyError, NameError):
                        print(upload.json())
                        raise RuntimeError('Upload failed - try manually!')
                else:
                    print(upload.json())
                    raise RuntimeError('Upload failed - try manually!')

    def run(self):
        try:
            with open(self.EAP_CONFIG_FILENAME):
                self.read_config()
        except FileNotFoundError:
            print('No configuration file found!')
            return 0
        filename = self.download_jpg()

        try:
            session, self.token = self.get_token()
            #self.upload_file(session, self.ds_fn)
        except (RuntimeError, HTTPError) as e:
            print(e)
            print('Could not upload file. Please verify your credentials.')

        return 1


    def __init__(self):
        self.rotation = 0
        self.url = ''
        self.username = ''
        self.password = ''
        self.summary = 'Uploaded via dspace2PDF'
        self.title = ''
        self.description = ''
        self.author = ''
        self.token = ''
        self.date = ''
        self.license = ''
        self.filename = ''
        self.ds_fn = ''


if __name__ == '__main__':
    start_time = time.time()
    downloaded = EAPBookFetch().run()
    elapsed_time_secs = time.time() - start_time
    print("Uploaded " + str(downloaded) + " files in " + str(elapsed_time_secs) + " seconds")
