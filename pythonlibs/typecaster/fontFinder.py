"""

Typecaster's submodule for functionality related to locating fonts, identifying their basic properties, and building interfaces for them.
The general goal of this submodule is to provide tools for identifying available fonts and offer different ways of exposing them to the user.

"""

from __future__ import annotations
import json
from find_system_fonts_filename import get_system_fonts_filename
from pathlib import Path, WindowsPath, PosixPath
from fontTools import ttLib
from platform import system as get_platform_system
from typecaster.config import get_config, add_config_dependencies

# Suppress name table errors by disabling logging.
import logging
# This is a pretty brute-force solution so it might have unintended consequences for working with logging.
logging.disable(logging.ERROR)
# This method should be a bit more precise (...but it doesn't work for some reason)
# logging.getLogger("fonttools.ttLib.tables._n_a_m_e").setLevel(logging.CRITICAL + 1)


PLATFORM = get_platform_system().upper()

_families_ = {}
_name_info_ = {}
_path_to_name_mappings_ = {}
add_config_dependencies(_families_, _name_info_, _path_to_name_mappings_)

COLLECTIONSUFFIXES = {".ttc", ".otc"}
FONTFILES = {".ttf": "", ".ttc": "", ".otf": "", ".otc": "", ".woff": "", ".woff2": ""}
FONT_FIND_MAX_DEPTH = 3

LIVETYPE_LOCATION = None
if PLATFORM == "WINDOWS":
    LIVETYPE_LOCATION = Path.home() / "AppData/Roaming/Adobe/CoreSync/plugins/livetype"
elif PLATFORM == "DARWIN":
    LIVETYPE_LOCATION = Path.home() / "Library/Application Support/Adobe/CoreSync/plugins/livetype"
elif PLATFORM == "LINUX":
    LIVETYPE_LOCATION = None

# --------------------------------------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------------------------------------

# Fontfinder utilities

# --------------------------------------------------------------------------------------------------------------------------------

try:
    from hou import text
    def to_real_path(path:str)->Path:
        """Take a path string with variables and convert it to a pathlib path.
        This will evaluate the string in a way as close to Houdini as possible.

        Args:
            path (str): Pathstring to convert

        Returns:
            Path: Path object which has had it's variables expanded and been fully resolved
        """
        # from os.path import expandvars
        # print( "Style-Houdini:", Path(text.expandString(path)).resolve() )
        # print( "Style-Hybrid :", Path(text.expandString(str=path,expand_tilde=False)).expanduser().resolve() )
        # print( "Style-Pathlib:", Path(expandvars(path)).expanduser().resolve() )
        return Path(text.expandString(path)).resolve()

except ImportError:
    from os.path import expandvars
    def to_real_path(path:str)->Path:
        """Take a path string with variables and convert it to a pathlib path.
        This is a fallback if being run outside of Houdini.

        Args:
            path (str): Pathstring to convert

        Returns:
            Path: Path object which has had it's variables expanded and been fully resolved
        """
        return Path(expandvars(path)).expanduser().resolve()


def __clear_font_caches__():
    _families_.clear()
    _name_info_.clear()
    _path_to_name_mappings_.clear()


class NameInfo:
    """
    This should have pretty similar behavior to a NamedTuple,
    although I've made almost none of the same performance considerations.
    Treating this as a list now requires two dictionary lookups, which is certainly slower by many orders of magnintude.

    But since I haven't touched __getattr__ in any way, performance should be the same as a normal class when treated as a normal one
    """
    def __init__( self,
                path: Path,
                number: int,
                family: str,
                subfamily: str = "Regular",
                relative_path: str|Path = None,
                tags: dict={},
                interface_path: str = None ):
        self.path = path
        self.number = number
        self.family = family
        self.subfamily = subfamily
        self.relative_path = relative_path
        self.tags = tags

        if not interface_path:
            if relative_path:
                if isinstance( relative_path, Path):
                    self.interface_path = self.relative_path.as_posix()
                else:
                    self.interface_path = relative_path
            else:
                self.interface_path = self.path.as_posix()
        else:
            self.interface_path = interface_path

        # self.__field_names__ = list(map(str, self.__dict__.keys() ))
        # self._list_  = []
        # for name in self.__field_names__:
        #     self._list_.append( self.__dict__[name] )
    
    def __repr__(self):
        repr_fmt = '(' + ', '.join(f'{name}={repr(self.__dict__[name])}' for name in self.__field_names__) + ')'
        'Return a nicely formatted representation string'
        return self.__class__.__name__ + repr_fmt
    
    def __getitem__(self, item):
        # return self._list_[item]
        if isinstance(item, int):
            return self.__dict__[ self.__field_names__[item] ]
        elif isinstance(item, str):
            return self.__dict__[item]
    
    def __setitem__(self, item, value):
        if isinstance(item, int):
            self.__dict__[ self.__field_names__[item] ] = value
        if isinstance(item, str):
            self.__setattr__( item, value)
    
    def __setattr__(self, name, value):
        if not hasattr(self, '__field_names__'):
            self.__dict__['__field_names__'] = []
        if name not in self.__dict__:
            self.__field_names__.append(name)
        super.__setattr__( self, name, value)
    
    def __len__(self):
        return len(self.__field_names__)
    
    def to_json(self):
        return self.__repr__()
    # def __dict__(self):
    #     dict = { k: self.__dict__[k] for k in self.__field_names__}
    #     return dict

    # def __iter__(self):
    #     d = {}
    #     for name in self.__field_names__:
    #         val = self.__dict__[name]
    #         d.update( [(name, val ),] )    # reuses stored hash values if possible
    #     return iter(d)


# EmptyInfo = NameInfo(path=None,number=None,family=None)

def get_best_names(ttfont:ttLib.TTFont)->tuple[str,str,str]:
    """Get the best names from a TTFont object

    Args:
        ttfont (ttLib.TTFont): Font to read names from

    Returns:
        tuple[str,str,str]: Tuple of names associated with the font, ordered as (Name, Family, Subfamily).
    """
    name = ""
    family = ""
    nametable = ttfont['name']
    name = nametable.getBestFullName()
    family = nametable.getBestFamilyName()
    subfamily = nametable.getBestSubFamilyName()

    # FONT_SPECIFIER_NAME_ID = 4
    # FONT_SPECIFIER_FAMILY_ID = 1
    # def decode(rec):
    #     return str(rec)
    #     # TODO should this be necessary?
    #     try:
    #         return rec.string.decode("utf-8")
    #     except UnicodeDecodeError:
    #         return rec.string.decode("utf-16-be")
    # 
    # for record in ttfont['name'].names:
    #     if record.nameID == FONT_SPECIFIER_NAME_ID and not name:
    #         name = decode(record)
    #     elif record.nameID == FONT_SPECIFIER_FAMILY_ID and not family:
    #         family = decode(record)
    #     if name and family:
    #         break
    return name, family, subfamily

# Below is an experimental idea for dumping all of the font info to a json file.
# It could be potentially useful to get the information from this when Houdini has many python
# sessions running in something like PDG, where the initial time to locate all of the fonts
# could be meaningful (assuming that the workers are having their python state reset)
def __info_to_jsondump__(to_file=False, file_path="$TYPECASTER/.temp/fontFinder_cache.json", indent=4):
    """Dump the the primary font info to JSON.

    Args:
        to_file (bool, optional): Output to a file. Defaults to False.
        file_path (str, optional): File path to write to. Defaults to "/.temp/fontFinder_cache.json".
        indent (int, optional): Number of indents to use when formatting. Defaults to 4.

    Returns:
        str|None: If to_file was False, the JSON will be returned as a string. Otherwise nothing will be returned.
    """
    # Monkeypatching method of complex object compatibility taken from
    # this stackoverflow answer: https://stackoverflow.com/a/38764817
    # from json import JSONEncoder, dump as jsondump, dumps as jsondumps
    def _default(self, obj):
        return getattr(obj.__class__, "to_json", _default.default)(obj)
    _default.default = json.JSONEncoder().default
    json.JSONEncoder.default = _default
    
    data = {'name_info': name_info(), 'families': families(), 'path_to_name_mappings':path_to_name_mappings() }
    if to_file:
        path = to_real_path(file_path)
        path.parent.mkdir(exist_ok=True)
        with path.open("w") as f:
            json.dump(data, f, indent=indent)
    else:
        return json.dumps(data,indent=indent)

# --------------------------------------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------------------------------------

# Font searching and cache creation

# --------------------------------------------------------------------------------------------------------------------------------

def __cache_individual_font__(font:ttLib.TTFont, path:Path, tags:dict={}, number=0, relative_path:str=None):
    """Add an single font to the relevant caches (if it doesn't already exist)

    Args:
        font (ttLib.TTFont): Font object to operate on
        path (Path): Path to the font
        tags (dict, optional): Useful information which can help search and categorize fonts. Optional. Defaults to {}.
        number (int, optional): Font number. Used with font collections. Defaults to 0.
        relative_path (str, optional): Relative path to the font. Useful for interfaces and other parts where you don't want to break the relative pathing of a specified font. Defaults to None.
    """
    path = path.resolve()

    if LIVETYPE_LOCATION and path.is_relative_to(LIVETYPE_LOCATION) and tags.get('source',None) is None:
        tags['source'] = 'Adobe'

    if 'variable' not in tags and font.get("fvar"):
        tags['variable'] = True

    names = get_best_names(font)
    fontName = names[0]
    fontFamily = names[1]
    fontSubFamily = names[2]

    if fontName not in _name_info_:
        _name_info_[fontName] = NameInfo( path, number, fontFamily, subfamily=fontSubFamily, tags=tags, relative_path=relative_path )
    
    posixpath = path.as_posix()
    if posixpath not in _path_to_name_mappings_:
        _path_to_name_mappings_[posixpath] = {number:fontName}
    else:
        if number not in _path_to_name_mappings_[posixpath]:
            _path_to_name_mappings_[posixpath][number] = fontName

    # Maybe this should be a set since I don't want repeated items anyways?
    if fontFamily not in _families_:
         _families_[fontFamily] = [fontName,]
    else:
        if fontName not in _families_[fontFamily]:
            _families_[fontFamily].append(fontName)

def __iterate_over_fontfiles__(found_fonts:list[str]):
    """Iterate over a list of path strings and add them to the cache, handling any font collection files found as well.

    Args:
        found_fonts (list[str]): List of font paths to operate on. This list currently is assumed to only contain valid paths.
    """
    # TODO: Should there be error handling here? Or can we assume the incoming paths are valid fonts. 
    for f in found_fonts:
        p  = Path(f)
        if p.suffix.lower() in COLLECTIONSUFFIXES:
            # print( f"{p.name} is a collection!" )
            collection = ttLib.TTCollection(p)
            for number, ttfont in enumerate(collection.fonts):
                __cache_individual_font__( ttfont, p, tags={}, number=number)
        else:
            ttfont = ttLib.TTFont(p, fontNumber=0)
            __cache_individual_font__( ttfont, p, tags={}, number=0)

def _SearchDir( searchpath:Path, depth:int=0, max_depth:int=3):
    """
    Search through a path and return a list of the fonts found within.
    """
    results = []
    for p in searchpath.iterdir():
        if p.is_dir() and depth < FONT_FIND_MAX_DEPTH and depth < max_depth and p.suffix != ".ufo":
            try:
                res = _SearchDir(p, depth=depth+1, max_depth=max_depth)
                if res:
                    results.extend(res)
            except PermissionError:
                pass
        else:
            if p.suffix in FONTFILES:
                results.append(p)
    return results

def _IterDir( searchpath:Path, function, depth:int=0, max_depth:int=3, confirm_fontfile:bool=True):
    """
    Iterate over the possible font files found within a path.
    """
    if not max_depth:
        max_depth = FONT_FIND_MAX_DEPTH
    elif max_depth > FONT_FIND_MAX_DEPTH:
        max_depth = FONT_FIND_MAX_DEPTH

    if searchpath.is_dir():
        for p in searchpath.iterdir():
            if p.is_dir() and depth < max_depth and p.suffix != ".ufo":
                try:
                    _IterDir(p, function=function, depth=depth+1, max_depth=max_depth, confirm_fontfile=confirm_fontfile)
                except PermissionError:
                    pass
            else:
                if confirm_fontfile is False or p.suffix in FONTFILES:
                    function(p)
    else:
        if confirm_fontfile is False or searchpath.suffix in FONTFILES:
            function(searchpath)

def __add_adobe_fonts__():
    def iterFunc(p:Path):
        if p.is_file() and p.suffix == '':
            try:
                font = ttLib.TTFont(p)
                __cache_individual_font__(font, p, tags={'source':'Adobe'})
            except ttLib.TTLibError:
                pass

    if LIVETYPE_LOCATION:
        _IterDir( LIVETYPE_LOCATION, function=iterFunc, max_depth=1, confirm_fontfile=False)

def __add_fonts_from_relative_path__(relative_path:str, tags={}, max_depth=None, real_path:Path=None):
    if not real_path:
        real_path = to_real_path(relative_path)
    if real_path.exists():
        def iterFunc(p:Path):
            if p.is_file():
                try:
                    font = ttLib.TTFont(p)
                    relfile = p.relative_to(real_path).as_posix()
                    if relfile != '.':
                        relpath = f"{relative_path}/{relfile}"
                    else:
                        relpath = relative_path
                    __cache_individual_font__(font, path=p, tags=tags, relative_path=relpath)
                except ttLib.TTLibError:
                    pass
        _IterDir( real_path, function=iterFunc, max_depth=max_depth)

def __add_fonts_from_relative_paths__( pathset:tuple ):
    for pathdat in pathset:
        __add_fonts_from_relative_path__( real_path=pathdat[0], relative_path=pathdat[1], tags={'source':pathdat[2]}, max_depth=pathdat[3] )

def __get_searchpaths__( config:dict=None)-> tuple[list,list,list]:
    prior_first = []
    prior_standard = []
    prior_last = []
    if not config:
        config = get_config()
    if 'searchpaths' in config:
        searchpaths = config['searchpaths']
        if isinstance(searchpaths, dict):
            for platform in searchpaths:
                if platform.upper() in ('ALL', PLATFORM):
                    for searchinfo in searchpaths[platform]:
                        path = None
                        sourcetag = None
                        max_depth_override = min(FONT_FIND_MAX_DEPTH, 2)
                        priority = 0
                        if isinstance( searchinfo, str):
                            path = searchinfo

                        elif isinstance( searchinfo, dict):
                            path = searchinfo.get('path',None)
                            sourcetag = searchinfo.get('source_tag', None)
                            max_depth_override = searchinfo.get('max_depth_override', max_depth_override)
                            priority = searchinfo.get('priority',priority)

                        elif isinstance( searchinfo, list):
                            path = searchinfo[0]
                            length = len(searchinfo)
                            if length > 1:
                                sourcetag = searchinfo[1]
                                if length > 2:
                                    priority = searchinfo[2]

                        if path:
                            relpath = path
                            path = to_real_path(path)
                            if path.exists():
                                relpath = Path(relpath).as_posix()

                                data = (path, relpath, sourcetag, max_depth_override, priority)
                                if priority == 0:
                                    prior_standard.append( data)
                                elif priority > 0:
                                    prior_first.append( data)
                                elif priority < 0:
                                    prior_last.append( data)
    if prior_first:
        prior_first.sort( key= lambda k: k[4], reverse=True )
    if prior_last:
        prior_last.sort( key= lambda k: k[4], reversed=True )
    return prior_first, prior_standard, prior_last


def update_font_info():
    """Search through all of the defined font search paths and rebuild all of
    the information associated with the fonts that are found.
    
    This will query the current config values, but will NOT get new config values.
    """
    # print("Updating Typecaster font info")
    __clear_font_caches__()
    config = get_config()
    
    custom_searchpaths = __get_searchpaths__(config)
    __add_fonts_from_relative_paths__( custom_searchpaths[0] )

    if config.get('only_use_config_searchpaths', 0) == 0:

        # get_system_fonts_filename actually locates some of the adobe fonts,
        # but it doesn't seem to get all, so running this is still useful
        __add_adobe_fonts__()
        # __add_fonts_from_relative_path__("$HFS/houdini/fonts", tags={'source':'$HFS'})
        # __add_fonts_from_relative_path__("$TYPECASTER/fonts", tags={'source':'$TYPECASTER'})
        # __add_fonts_from_relative_path__("$HIP/fonts", tags={'source':'$HIP'})
        # __add_fonts_from_relative_path__("$JOB/fonts", tags={'source':'$JOB'})

        found_fonts = get_system_fonts_filename()
        __iterate_over_fontfiles__(found_fonts)


    __add_fonts_from_relative_paths__( custom_searchpaths[1] )
    __add_fonts_from_relative_paths__( custom_searchpaths[2] )

    # If No fonts were found (highly unlikely), add a fake font so that the
    # cache checkers don't endlessley refresh
    if not _families_ or not _name_info_ or not _path_to_name_mappings_:
        msg = 'Typecaster-NoFontsFound'
        _families_[msg] = [msg,]
        _name_info_[msg] = NameInfo( Path(msg), 0, msg )
        _path_to_name_mappings_[Path(msg)] = {0:msg}


# --------------------------------------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------------------------------------

# Font information retrieval

# --------------------------------------------------------------------------------------------------------------------------------

def __lookup_if_specified__( dict:dict, key, default=None)->(dict|str|NameInfo):
    """Utility function which returns either the value of a dictionary, or the dictionary itself, 
    depending on if a key is given."""
    return dict if key is None else dict.get(key, default)

def families(family:str=None) -> (dict[str]|list):
    """Returns a dictionary with key-value pairs of font families and their fonts.
    This will also initialize all related values if they haven't been already."""
    if not _families_:
        update_font_info()
    return __lookup_if_specified__(_families_, family)

def name_info(name:str=None) -> (dict[str,NameInfo]|NameInfo):
    """
    Get all the information associated with a font name.
    If a font name is given, a corrensponding NameInfo object will be directly returned.
    Otherwise, a dictionary of all name infos will be returned, with the keys being the font names.
    Args:
        name(str, optional): The name of the font you would like the information for. Defaults to None.
        
    This will also initialize all related values if they haven't been already.
    """
    if not _name_info_:
        update_font_info()
    return __lookup_if_specified__(_name_info_, name)


def path_to_name_mappings(path:Path|str=None) -> (dict[Path,dict[int,str]]|dict[int,str]):
    """
    Used for converting a path to a dict of font names, structured as key-value pairs of
    numbers and names. If the path is to a single font, the dict will only have one
    element. If the path is to a collection, the dict will have all of the font names
    for the collection.
    
    Args:
        path(Path, optional): The specific path you would like to look up. Defaults to None.
    
    Returns:
        dict[Path,dict[int,str]]|dict[int,str]: If no argument is given, this returns a 
            dictionary which will give the dictionary of font names for a given path 
            (if it exists). If a path is specified, the result of the dictionary will be
            returned.

    This will also initialize all related values if they haven't been already.
    """
    if not _path_to_name_mappings_:
        update_font_info()
    if path and isinstance( path, Path):
        path = path.as_posix()
    return __lookup_if_specified__(_path_to_name_mappings_, path)


# # --------------------------------------------------------------------------------------------------------------------------------
# # --------------------------------------------------------------------------------------------------------------------------------
# # UNUSED
# # Search from config file
# # UNUSED
# # --------------------------------------------------------------------------------------------------------------------------------

# def __getSearchConfig__()->str:
#     """
#     Combine the current hipfile's search string with the one stored in the config file
#     """

#     os.getenv('TYPECASTER_SEARCHPATHS')

#     raise NotImplementedError()

# def search_custom_dirs()->tuple[Path,str]:
#     """
#     #### Read a persistent environment variable saved with the current HIP.

#     If it is present, it will be in 1 of 2 value configurations:
#     1) A value which indicates that a config file should be read for the search directories
#     2) A set of string paths (both relative and not) to iterate though.
#         These paths can either append or remove values from the paths in the config file

#         Example config syntax:
#             ||$Path/to/FOLDER|ALL|+|R3||
#             ||$Path/to/FOLDER|ALL|+|R3||C://Andrew/Downloads/path/to/FOLDER|WIN|+|R3||

#         RESULT:
#             All of the folders will be searched, except for the $JOB/fonts folder, which was removed
#             from the search directories using the rules in the project config

#     From here, all of the directories will be iterated over, checking for any valid font files.
#     """
#     foundfonts = []

#     fontconfigs = __getSearchConfig__().split("||")
#     for fontconfig in fontconfigs:
#         if fontconfig and fontconfig != "\n":
#             configs = fontconfig.split("|")
#             if len(configs) > 1:
#                 relpath = Path(configs[0]).as_posix()
#                 searchpath = to_real_path(relpath)

#                 if searchpath.exists():
#                     if True:
#                         fontfiles = _SearchDir( searchpath, depth=0)
#                         for f in fontfiles:
#                             fposix = f.as_posix()
#                             frelpath = relpath+fposix.replace(searchpath.as_posix(), "")
#                             foundfonts.append( (fposix, frelpath ) )
#                     else:
#                         print(f"Found folder {searchpath.as_posix()} from {relpath}")
#                         for d in searchpath.iterdir():
#                             if d.suffix.lower() in FONTFILES:
#                                 print( d)
#                             elif d.is_dir():
#                                 print( "Folder:", d)
#     return foundfonts