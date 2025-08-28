import os
import tempfile

# from .ufoCompiler import compileUFOToPath as ufo_compileUFOToPath
from .dsCompiler import compileDSToPath as ds_compileDSToPath
from .ttxCompiler import compileTTXToPath as ttx_compileTTXToPath

# def compileUFOToPath(ufoPath, ttPath, outputWriter):
#     return ufo_compileUFOToPath( os.fspath(ufoPath), os.fspath(ttPath), )

# # FIXME: Ok so while the ufo doesn't error anymore and some of the font is created, the actual glyph paths appear to be empty.
# def compileUFOToBytes(ufoPath, outputWriter):
#     tmp = tempfile.NamedTemporaryFile(prefix="fontgoggles_temp", suffix=".ttf")
#     tmp.close()
#     compileUFOToPath(ufoPath, tmp.name, outputWriter)
#     with open(tmp.name, "rb") as f:
#         fontData = f.read()
#         if not fontData:
#             fontData = None
#     if tmp:
#         tmp.close()
#         os.unlink(tmp.name)
#     return fontData


def compileDSToPath(dsPath, fontNumber, ttFolder, ttPath, outputWriter):
    return ds_compileDSToPath(os.fspath(dsPath), str(fontNumber), os.fspath(ttFolder), os.fspath(ttPath),)

def compileDSToBytes(dsPath, fontNumber, ttFolder, outputWriter):
    tmp = tempfile.NamedTemporaryFile(prefix="fontgoggles_temp", suffix=".ttf")
    tmp.close()
    compileDSToPath(dsPath, fontNumber, ttFolder, tmp.name, outputWriter)
    with open(tmp.name, "rb") as f:
        fontData = f.read()
        if not fontData:
            fontData = None
    if tmp:
        tmp.close()
        os.unlink(tmp.name)
    return fontData


def compileTTXToPath(ttxPath, ttPath, outputWriter):
    return ttx_compileTTXToPath( os.fspath(ttxPath), ttPath)

def compileTTXToBytes(ttxPath, outputWriter):
    tmp = tempfile.NamedTemporaryFile(prefix="fontgoggles_temp", suffix=".ttf")
    tmp.close()
    compileTTXToPath(ttxPath, tmp.name, outputWriter)
    with open(tmp.name, "rb") as f:
        fontData = f.read()
        if not fontData:
            fontData = None
    if tmp:
        tmp.close()
        os.unlink(tmp.name)
    return fontData