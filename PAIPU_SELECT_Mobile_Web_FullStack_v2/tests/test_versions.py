import base64
import json
from pathlib import Path

import pytest
import version_resolver as versions


def test_actual_official_version_bundle_is_decoded():
    fixture=json.loads(Path(__file__).with_name('official_version_fixture.json').read_text())
    assert versions.read_resource_version(base64.b64decode(fixture['payload_base64']))==fixture['resource']


def test_version_sources_reject_nonofficial_hosts():
    for url in ['http://appstatic.mahjongsoul.com/x','https://appstatic.mahjongsoul.com.evil.test/x',
                'https://user:secret@appstatic.mahjongsoul.com/x','https://127.0.0.1/x']:
        with pytest.raises(versions.VersionError):versions.trusted_url(url)


@pytest.mark.asyncio
async def test_verified_live_hash_uses_recorded_resource_and_caches(monkeypatch):
    versions.CACHE.clear()
    expected=versions.MANIFEST['kr']
    calls=[]
    async def read(http,url,limit):
        calls.append(url)
        if url==versions.CLIENTS['kr']:return b'productVersion: "4.0.12"'
        if url.endswith('bundle_hash.txt'):return expected['bundle_hash'].encode()
        raise AssertionError('unchanged hash must not download a manifest')
    async def read_json(http,url):
        if 'clientbundlesettings' in url:
            return {'warehouses':[{'urls':[{'url':'https://appstatic.mahjongsoul.com','Priority':100}],
                                   'warehouseSettingPath':'/v4/kr/resources/warehouseSettings/kr-release.json'}]}
        return {'urls':[{'url':'https://appstatic.mahjongsoul.com'}],'bundlePath':'/v4/kr/resources/ab/'}
    monkeypatch.setattr(versions,'read',read)
    monkeypatch.setattr(versions,'read_json',read_json)
    first=await versions.resolve('kr');second=await versions.resolve('kr')
    assert first==second and first['resource']=='0.16.266'
    assert len(calls)==2
    versions.CACHE.clear()
