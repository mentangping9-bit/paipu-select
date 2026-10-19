"""Read the resource version from the official Unity resource distribution.

HTML productVersion is NOT the resource version. Resolve the GameLoader settings
chain, verify the live bundle hash, and read docs_version/version.json when it
changes. No account credentials are involved in any request in this module.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import struct
import threading
import time
from urllib.parse import urljoin, urlsplit

import aiohttp

MANIFEST = json.loads(Path(__file__).with_name('client_versions.json').read_text())['regions']
CLIENTS = {'kr':'https://mahjongsoul.game.yo-star.com/kr/index.html',
           'en':'https://mahjongsoul.game.yo-star.com/', 'jp':'https://game.mahjongsoul.com/'}
HOSTS = {'game.mahjongsoul.com','mahjongsoul.game.yo-star.com',
         'appstatic.mahjongsoul.com','appstaticbk.mahjongsoul.com'}
CACHE = {}
CACHE_LOCK = threading.Lock()
TTL = 300
VERSION = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,5}$')


class VersionError(RuntimeError):
    pass


def trusted_url(url):
    u=urlsplit(url)
    if u.scheme!='https' or u.hostname not in HOSTS or u.port or u.username or u.password:
        raise VersionError('Untrusted version source')
    return url


async def read(http, url, limit):
    async with http.get(trusted_url(url), allow_redirects=False) as response:
        response.raise_for_status()
        parts=[];size=0
        async for part in response.content.iter_chunked(65536):
            size+=len(part)
            if size>limit:raise VersionError('Version source exceeds limit')
            parts.append(part)
        return b''.join(parts)


async def read_json(http,url):
    return json.loads(await read(http,url,1024*1024))


def best_host(entries):
    if not isinstance(entries,list) or not entries:raise VersionError('Missing CDN hosts')
    return trusted_url(max(entries,key=lambda item:(int(item.get('Priority',0)),int(item.get('weight',0))))['url'])


def settings_from_data(data):
    import UnityPy
    if not data.startswith(b'UnityWebData1.0\0') or len(data)<20:
        raise VersionError('Invalid Unity data header')
    end=struct.unpack_from('<I',data,16)[0];pos=20
    if not 20<=end<=len(data):raise VersionError('Invalid Unity data directory')
    bundle=None
    while pos<end:
        if pos+12>end:raise VersionError('Invalid Unity data entry')
        offset,size,n=struct.unpack_from('<III',data,pos);pos+=12
        if pos+n>end or offset+size>len(data):raise VersionError('Invalid Unity data bounds')
        name=data[pos:pos+n].decode('utf-8');pos+=n
        if name.endswith('.unity3d'):bundle=data[offset:offset+size];break
    if bundle is None:raise VersionError('Client bundle missing')
    for obj in UnityPy.load(bundle).objects:
        if obj.type.name!='MonoBehaviour':continue
        raw=obj.get_raw_data()
        for match in re.finditer(rb'https?://[^\x00\s<>\"\x01-\x1f]{5,250}',raw):
            if b'clientbundlesettings' not in match.group().lower() or match.start()<4:continue
            n=struct.unpack_from('<I',raw,match.start()-4)[0]
            if not 10<=n<=512 or match.start()+n>len(raw):continue
            return trusted_url(raw[match.start():match.start()+n].decode('utf-8'))
    raise VersionError('GameLoader settings URL missing')


def version_bundle_name(raw):
    import UnityPy
    UnityPy.config.FALLBACK_UNITY_VERSION='2022.3.62f2c1'
    for obj in UnityPy.load(raw).objects:
        if obj.type.name!='MonoBehaviour':continue
        tree=obj.read_typetree()
        for item in tree.get('assetInfos',[]):
            if item.get('assetPath')=='MyAssets/docs_version/version.json':
                name=tree['bundleInfos'][item['ownerBundleIndex']]['name']
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',name):raise VersionError('Invalid version bundle name')
                return name
    raise VersionError('Resource version asset missing')


def read_resource_version(raw):
    import UnityPy
    UnityPy.config.FALLBACK_UNITY_VERSION='2022.3.62f2c1'
    for obj in UnityPy.load(raw).objects:
        if obj.type.name!='TextAsset':continue
        asset=obj.read()
        if asset.m_Name!='version':continue
        data=json.loads(asset.m_Script)
        resource=data.get('version','')
        if not VERSION.fullmatch(resource) or data.get('platform')!='WebGL':
            raise VersionError('Invalid resource version')
        return resource
    raise VersionError('Resource version text missing')


async def resolve(region):
    if region not in CLIENTS:raise VersionError('Unsupported region')
    with CACHE_LOCK:
        cached=CACHE.get(region)
        if cached and time.monotonic()-cached['checked_at']<TTL:return cached.copy()
    baseline=MANIFEST[region]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25),trust_env=True) as http:
        html=(await read(http,CLIENTS[region],1024*1024)).decode('utf-8-sig')
        match=re.search(r'productVersion\s*:\s*"([0-9.]+)"',html)
        if not match or not VERSION.fullmatch(match[1]):raise VersionError('Client product version missing')
        product=match[1]
        settings=baseline.get('settings_url') if product==baseline['product'] else None
        if not settings:
            # New product build: take its data file from the official HTML.
            file=re.search(r'var\s+dataFile\s*=\s*"(/[^"\s]+\.data\.gz)"',html)
            build=re.search(r'var\s+buildUrl\s*=\s*"([^"\s]+)"',html)
            if not file or not build:raise VersionError('Client data URL missing')
            url=urljoin(CLIENTS[region],build[1].rstrip('/')+'/'+file[1].lstrip('/'))
            settings=await asyncio.to_thread(settings_from_data,await read(http,url,32*1024*1024))
        config=await read_json(http,settings)
        warehouse=config['warehouses'][0]
        settings_url=urljoin(best_host(warehouse['urls']),warehouse['warehouseSettingPath'])
        distribution=await read_json(http,settings_url)
        base=urljoin(best_host(distribution['urls']),distribution['bundlePath']).rstrip('/')+'/WebGL/ASTC/'
        bundle_hash=(await read(http,base+'bundle_hash.txt',128)).decode().strip()
        if not re.fullmatch(r'[0-9a-f]{32,64}',bundle_hash):raise VersionError('Invalid bundle hash')
        if bundle_hash==baseline.get('bundle_hash') and product==baseline['product']:
            resource=baseline['resource']
        else:
            name=await asyncio.to_thread(version_bundle_name,await read(http,base+'bundle_info_so.majset',4*1024*1024))
            resource=await asyncio.to_thread(read_resource_version,await read(http,base+name,256*1024))
    result={'product':product,'resource':resource,'bundle_hash':bundle_hash,'checked_at':time.monotonic()}
    with CACHE_LOCK:CACHE[region]=result
    return result.copy()


def status():
    with CACHE_LOCK:
        return {region:{key:value for key,value in item.items() if key!='checked_at'}
                for region,item in CACHE.items()}
