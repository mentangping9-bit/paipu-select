"""Exercise the actual protobuf -> tensoul -> HTTP JSON boundary, without auth.

Small anonymous protobuf fixture from honvl/Majsoul-to-NAGA, itself adapted from
AsaChiri/majsoul-naga under MIT; see LICENSE-converter-fixture. No account tokens.
"""
import base64
import json
from pathlib import Path
import subprocess

from ms.protocol_pb2 import ResGameRecord
from paipu_vendor.mahjong_url_parser.sources.majsoul import _convert_record
from server import check_tenhou


def test_actual_converter_output_is_json_normalized_and_frontend_readable(tmp_path):
    record=ResGameRecord()
    record.ParseFromString(base64.b64decode(Path(__file__).with_name('converter_record.res.b64').read_text()))
    produced=_convert_record(record)
    assert isinstance(produced['log'][0][0],tuple), 'keep a real tuple regression fixture'
    normalized=check_tenhou(produced)
    assert isinstance(normalized['log'][0][0],list)
    assert all(isinstance(hand[16],list) for hand in normalized['log'])
    assert json.dumps(normalized,ensure_ascii=False)==json.dumps(produced,ensure_ascii=False)
    payload=tmp_path/'converted.json';payload.write_text(json.dumps(normalized))
    result=subprocess.run(['node',str(Path(__file__).with_name('check.js')),str(payload)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
