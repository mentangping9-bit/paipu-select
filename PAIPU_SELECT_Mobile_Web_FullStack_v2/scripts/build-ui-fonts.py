"""Build local OFL font subsets for UI copy. Usage: python scripts/build-ui-fonts.py SOURCE_DIR

SOURCE_DIR contains NanumSquareRoundR.ttf, ZenMaruGothic-Medium.ttf and nunito.ttf.
Requires fonttools[woff] (development only). See DESIGN_ASSETS.md for upstreams.
"""
from pathlib import Path
import sys
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1])
# UI translations supply the CJK characters. New UI copy requires regenerating
# subsets; unsupported dynamic text continues to use the system font fallback.
text = ''.join(p.read_text() for p in (root / 'public').glob('*.js'))
text += (root / 'public/index.html').read_text()
text += ''.join(map(chr, range(32, 127))) + '·…–—「」『』【】、。！？'
fonts = [
    ('NanumSquareRoundR.ttf', 'nanum-square-round-ko.woff2', 'Paipu Soft Round Korean', None),
    ('ZenMaruGothic-Medium.ttf', 'rounded-ja.woff2', 'Paipu Rounded Japanese', None),
    ('nunito.ttf', 'rounded-en.woff2', 'Paipu Rounded Latin', 600),
]
for filename, output, family, weight in fonts:
    font = TTFont(source / filename)
    if weight:
        font = instantiateVariableFont(font, {'wght': weight}, inplace=True)
    options = subset.Options()
    options.flavor = 'woff2'
    sub = subset.Subsetter(options=options)
    sub.populate(text=text)
    sub.subset(font)
    # Derived subsets receive distinct family names; license metadata is retained.
    names = {1: family, 2: 'Regular', 3: family + ' UI subset', 4: family,
             6: family.replace(' ', ''), 16: family, 17: 'Regular'}
    for record in font['name'].names:
        if record.nameID in names:
            record.string = names[record.nameID].encode(record.getEncoding())
    font.recalcTimestamp = False
    font.flavor = 'woff2'
    path = root / 'public/assets' / output
    font.save(path)
    print(output, path.stat().st_size)
