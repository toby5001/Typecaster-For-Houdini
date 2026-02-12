"""

Submodule for working with individual fonts in Typecaster.
If you want to access individual font information beyond what
typecaster.FontFinder provides, this is the best way to do so.

"""

import sys
from importlib import import_module
from typecaster.fontFinder import path_to_name_mappings, T1FONTFILES
from fontgoggles import font as fgfont
from fontTools.ttLib import TTLibError
from pathlib import Path
from functools import cached_property


class FontInitFailure(Exception):
    """Generic exception for when a font is unable to be initialized."""
    pass


class FontNotFoundException(FontInitFailure):
    pass


def getOpener(fontPath: Path, openerKey=None):
    """Get the correct opener for fontgoggles. Unlike the original function,
    the font is assumed to be valid by the time this function is called.

    Args:
        fontPath (Path): Path to a valid font.

    Returns:
        _type_: The font opener class used by fontgoggles to load a specific font type.
    """
    if not openerKey:
        openerKey = fgfont.sniffFontType(fontPath)
        if openerKey is None:
            if path_to_name_mappings(fontPath):
                openerKey = "otf"
        if openerKey is None:
            raise FontInitFailure("Unexpected file type!")
    elif openerKey not in fgfont.fontOpeners:
        raise FontInitFailure("Unexpected file type!")
    openerSpec = fgfont.fontOpeners[openerKey][1]
    moduleName, className = openerSpec.rsplit(".", 1)
    module = import_module(moduleName)
    openerClass = getattr(module, className)
    return openerClass


FontCache = {}

# def clear_cache():
#     FontCache.clear()


class Font:
    """Main class for individual fonts, providing the main entrypoint to fontgoggles.font and important information."""

    def __init__(
        self,
        path,
        number=0,
    ):
        """Initialize a Font object. This should almost never be directly called.
        It is highly reccomended to call Font.Cacheable() instead
        """
        if isinstance(path, Path):
            self.path = path
        else:
            self.path = Path(path)
        if not self.path.exists():
            raise FontNotFoundException("File doesn't exist.")

        if self.path.suffix.lower() in T1FONTFILES:
            print(
                f"<TYPECASTER WARNING> Triggered T1-->OTF font conversion for [{self.path}]. T1 Font handling is unfinished and is not yet at parity with the native Font node."
            )
            self.path = convert_t1_to_otf(self.path)
            opener = getOpener(self.path, openerKey="otf")
        else:
            opener = getOpener(self.path)
        self.font = opener(self.path, number)
        self.font.cocoa = False
        self._loaded = False
        self.load()

        self._variations = self.font.ttFont.get("fvar")
        self._variations_ctf = None
        self._instances = None
        self._instances_scaled = None

        self.best_line_spacing = self.get_best_line_spacing()
        self.bezier_order = self.get_bezier_order()

    def load(self):
        if self._loaded:
            return self
        else:
            try:
                self.font.load(sys.stderr.write)
                self._loaded = True
            except TTLibError:
                raise FontInitFailure("Unexpected TTLibError! Is this file valid?")
            return self

    def get_best_line_spacing(self) -> int:
        """
        Get the best line spacing, according to the available metrics in the specified font.
        This follows a similar order of spacing lookups to Microsoft's Word (I think).
        Falls back to using the unitsPerEm value if no other spacing could be identified.

        Returns:
            int: Best line spacing, in the font's designspace units.
        """
        """
        I'm not sure if I should be checking use_typo_metrics or just always try using it first.
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
        if not good:
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
    def general_glyph_height(self) -> int:
        """This property is used to create the general vertical bounding box for a glyph,
        which is currently used for vertical block alignment and glyph instancing point 
        locations (when not botom left). Since this information is very inconsistently 
        defined among fonts, it might be better to just calculate the bounding box of 
        each individual glyph.

        Returns:
            int: General glyph height
        """
        font = self.font.ttFont
        ascender = 0
        if os2 := font.get('OS/2'):
            ascender = os2.sCapHeight if hasattr(os2, "sCapHeight") else 0
             # if ascender == 0:
        #     # if cmap := font.getBestCmap():
        #     #     gname = cmap.get(ord("H"))
        #     #     hmtx = font.get('hmtx')
        #     #     if hmtx and gname:
        #     #         ascender = hmtx.metrics.get(gname,0)[0]
            if ascender == 0:
                ascender = os2.sTypoAscender if hasattr(os2, "sTypoAscender") else 0
        if ascender == 0:
            if hhea := font.get('hhea'):
                #     # raise NotImplementedError("It looks like some fonts don't always use OS/2. Is there a fallback besides a default value?")
                ascender = hhea.ascender if hasattr(hhea, "ascender") else 0
        if ascender == 0:
            ascender = 750
        return ascender

    def get_bezier_order(self):
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
        if self._variations_ctf is None:
            axes = {}
            if self._variations:
                fvar = self._variations
                for axis in fvar.axes:
                    axes[axis.axisTag] = axis.__dict__
            self._variations_ctf = axes
        return self._variations_ctf

    def instances(self, scaled=True):
        if self._instances_scaled and scaled:
            return self._instances_scaled
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
                    out[k] = (v - axis["minValue"]) / (
                        axis["maxValue"] - axis["minValue"]
                    )
                return out

            self._instances_scaled = {k: scale(v) for k, v in self._instances.items()}
            return self._instances_scaled

        return self._instances

    @staticmethod
    def Cacheable(path: Path, number=0):
        """Using a path and number, either retreive an existing font object, or create and cache a new one.
        While the functionality borrows significantly from coldtype.text.font.Font.Cacheable,
        this more cut-down version does very minimal checking for if the font is valid, only if the path exists.

        Args:
            path (Path): Path object to the font.
            number (int, optional): Used if the font path is to a collection to specify a particular font within. Defaults to 0.

        Raises:
            FontNotFoundException: Gets rasied if the path does not exist.

        Returns:
            Font: Returns a Font object.
        """
        actual_path = None
        if number > 0:
            # Incorporate the font number into the dict key, if needed
            actual_path = path
            path = f"{path}_#{number}"

        if path not in FontCache:
            FontCache[path] = Font(
                actual_path if actual_path else path, number=number
            ).load()
        return FontCache[path]


def convert_t1_to_otf(input_path: Path):
    """
    Converts a Type 1 font into a OpenType-CFF font.
    """
    # Right now this always runs (if the font wasn't already in FontCache).
    # Should I first check if the font has previously been converted?
    """
    Base conversion script made by Miguel Sousa
    https://gist.github.com/miguelsousa/66ee9504039a8b64c605defa316516c1
    """

    """
    I have no interest in creating a "bulletproof" conversion process, but I'd
    at least like to get close to parity with Houdini's native Font node.
    Known issues (which the native font node doesn't have):
    1) Some oblique/italic fonts turn into regular fonts when converted.
    2) Issues with nonstandard symbols being converted.
    3) Some pfb files fail to be parsed.
    """

    # I think I'd rather deal with the performance penalty of running these imports
    # multiple times rather than import all this even if a T1 font isn't ever used.
    from fontTools.t1Lib import T1Font
    from fontTools.pens.basePen import NullPen
    from fontTools.agl import toUnicode
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    import os
    import uuid

    try:
        t1 = T1Font(input_path)
        t1.parse()

        # Collect 'name' table strings
        font_name = t1.font.get("FontName", "")
        font_info = t1.font.get("FontInfo", {})
        full_name = font_info.get("FullName", "")
        font_version = font_info.get("version", "")
        name_strings = dict(
            familyName=font_info.get("FamilyName", ""),
            styleName=font_info.get("Weight", ""),
            fullName=full_name,
            psName=font_name,
            version=f"Version {font_version}",
            uniqueFontIdentifier=f"{font_version};{font_name}",
        )

        # Collect glyph names
        encoding = t1.font.get("Encoding")
        char_names = t1.font.get("CharStrings")
        gnames = []
        for gname in encoding:
            if gname not in gnames:
                gnames.append(gname)

        for gname in char_names:
            if gname not in gnames:
                gnames.append(gname)

        # Infer 'cmap' table values from glyph names
        cmap = {}
        for gname in gnames:
            char = toUnicode(gname)
            if char:
                cmap[ord(char)] = gname

        # Collect charstrings and advance widths
        char_strings = {}
        adv_widths = {}
        gset = t1.getGlyphSet()
        npen = NullPen()

        for gname in gnames:
            glyph = gset[gname]
            glyph.draw(npen)
            gwidth = round(glyph.width)
            adv_widths[gname] = gwidth
            t2pen = T2CharStringPen(gwidth, gset)
            glyph.draw(t2pen)
            cs = t2pen.getCharString()
            char_strings[gname] = cs

        fb = FontBuilder(1000, isTTF=False)
        fb.setupGlyphOrder(gnames)
        fb.setupCharacterMap(cmap)
        fb.setupCFF(font_name, {"FullName": full_name}, char_strings, {})

        lsb = {}
        for gname, cs in char_strings.items():
            xmin = 0
            gbbox = cs.calcBounds(None)
            if gbbox:
                xmin, *_ = gbbox
            lsb[gname] = xmin

        metrics = {
            gname: (adv_width, lsb[gname]) for gname, adv_width in adv_widths.items()
        }

        fb.setupHorizontalMetrics(metrics)
        fb.setupHorizontalHeader(ascent=1000, descent=-200)
        fb.setupNameTable(name_strings, mac=False)
        fb.setupOS2(sTypoAscender=1000, usWinAscent=1000, usWinDescent=200)
        fb.setupPost()

        temp_dir = os.environ.get("HOUDINI_TEMP_DIR")
        convertedpath = (Path(temp_dir) / "Typecaster/converted_fonts").resolve()
        convertedpath.mkdir(exist_ok=True, parents=True)
        # convertedpath /= input_path.stem+'.otf'
        # convertedpath /= str(hash(input_path.stem))
        convertedpath /= str(uuid.uuid5(uuid.NAMESPACE_DNS, input_path.stem))

        fb.save(convertedpath)
        return convertedpath.resolve()
    except Exception:
        # Catch all errors when running the conversion to prevent surfacing a python error to the user
        # There are so many ways that this operation can go wrong that it's better to just handle all
        # exceptions rather than catch specific ones.
        raise FontInitFailure("Failed to convert T1 font.")
