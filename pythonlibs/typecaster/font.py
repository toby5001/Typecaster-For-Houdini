import sys
from importlib import import_module
from typecaster.fontFinder import name_info, path_to_names
from functools import cached_property
from os import PathLike
from fontgoggles import font as fgfont
from pathlib import Path

def getOpener(fontPath: PathLike):
    openerKey = fgfont.sniffFontType(fontPath)
    if openerKey is None:
        tags = name_info( path_to_names(fontPath)[0] ).tags
        if tags.get('source','').lower() == 'adobe':
            openerKey = "otf"
        else:
            # font = ttLib.TTFont(fontPath)
            openerKey = "otf"
    assert openerKey is not None
    openerSpec = fgfont.fontOpeners[openerKey][1]
    moduleName, className = openerSpec.rsplit(".", 1)
    module = import_module(moduleName)
    openerClass = getattr(module, className)
    return openerClass

# ctf.getOpener = getOpener
# Font = ctf.Font
# FontNotFoundException = ctf.FontNotFoundException
# FontCache = ctf.FontCache

class FontNotFoundException(Exception):
    pass

FontCache = {}

# def clear_cache():
#     FontCache.clear()

class Font():
    # TODO support glyphs?
    def __init__(self,
        path,
        number=0,
        ):
        if isinstance(path, Path):
            self.path = path
        else:
            self.path = Path(path)
        if not self.path.exists():
            raise FontNotFoundException
        opener = getOpener(self.path)
        self.font = opener(self.path, number)
        # self.font:BaseFont = opener(self.path, number)
        self.font.cocoa = False
        self._loaded = False
        self.load()

        self._variations = self.font.ttFont.get("fvar")
        self._instances = None
    
    def load(self):
        if self._loaded:
            return self
        else:
            self.font.load(sys.stderr.write)
            self._loaded = True
            return self

    @cached_property
    def best_line_spacing(self)->int:
        """
        Get the best line spacing, according to the available metrics in the specified font.
        This follows a similar order of spacing lookups to Microsoft's Word (I think).
        Falls back to using the unitsPerEm value if no other spacing could be identified.

        Returns:
            int: Best line spacing, in the font's designspace units.
        """
        """
        I'm not sure if I should be checking use_typo_metrics or just always try using at first.
        Spacing priority ordering inspired by the following posts:
        https://silnrsi.github.io/FDBP/en-US/Line_Metrics.html
        https://www.high-logic.com/font-editor/fontcreator/tutorials/font-metrics-vertical-line-spacing
        """
        font = self.font.ttFont
        good = False
        if "OS/2" in font:
            os2 = font["OS/2"]
            use_typo_metrics = os2.fsSelection & 1 << 7
            if use_typo_metrics:
                sz = os2.sTypoAscender - os2.sTypoDescender + os2.sTypoLineGap
                if sz > 0:
                    good = True
            else:
                sz = os2.usWinAscent + os2.usWinDescent
                if sz > 0:
                    good = True
        if good != True:
            if "hhea" in font:
                hhea = font["hhea"]
                sz = hhea.ascender - hhea.descender + hhea.lineGap
                if sz > 0:
                    good = True
        if good:
            return sz
        else:
            return self.font.unitsPerEm

    @cached_property
    def bezier_order(self):
        # Set bezier order either from the sfntVersion or more often the font file's suffix
        # this will likely fail on a good amount of cases, but in 99% of the fonts I've tested, going by suffix works.
        sfntVersion = self.font.ttFont.reader.sfntVersion
        bezier_order = 3

        if sfntVersion == "OTTO":
            bezier_order = 4
        else:
            stem = self.path.suffix.lower()
            if stem == ".ttf":
                bezier_order = 3
            elif stem == ".otf":
                bezier_order = 4
            elif stem == ".woff":
                bezier_order = 3
            elif stem == ".woff2":
                bezier_order = 3
        return bezier_order

    def variations(self):
        axes = {}
        if self._variations:
            fvar = self._variations
            for axis in fvar.axes:
                axes[axis.axisTag] = (axis.__dict__)
        return axes
    
    def instances(self, scaled=True):
        if self._variations is None:
            return None
        
        if self._instances is None:
            self._instances = {}
            for x in self._variations.instances:
                name_id = x.subfamilyNameID
                name_record = self.font.ttFont["name"].getDebugName(name_id)
                self._instances[name_record] = x.coordinates
        
        if scaled:
            axes = self.variations()
            def scale(cs):
                out = {}
                for k, v in cs.items():
                    axis = axes[k]
                    out[k] = (v - axis["minValue"]) / (axis["maxValue"] - axis["minValue"])
                return out
            return {k:scale(v) for k, v in self._instances.items()}

        return self._instances

    @staticmethod
    def Cacheable( path:Path, number=0):
        actual_path = None
        if number > 0:
            # Incorporate the font number into the dict key, if needed
            actual_path = path
            path = f"{path}_#{number}"
        
        if path not in FontCache:
            FontCache[path] = Font(
                actual_path if actual_path else path,
                number=number).load()
        return FontCache[path]