"""

Submodule for functionality related to updating and parsing the interface of Typecaster HDAs, along with standalone interfaces.
Basically anything related to using interfaces to control Typecaster.

"""

from __future__ import annotations
import hou
import re
from typing import NamedTuple
from pathlib import Path, WindowsPath, PosixPath  # noqa: F401
from typecaster import fontFinder
from typecaster import font as tcf
from fontTools.ttLib import TTCollection
try:
    from PySide6 import QtWidgets, QtGui # type: ignore
    from PySide6.QtCore import Qt # type: ignore
    PS6 = True
except ModuleNotFoundError:
    from PySide2 import QtWidgets, QtGui
    from PySide2.QtCore import Qt
    PS6 = False
from fnmatch import fnmatch


# # This is kinda overkil to set as a standalone variable, but this is what ensures that varaxes are always houdini-readable
# ensure_compatible_name = hou.text.variableName
def ensure_compatible_name(name:str):
    """Process a string and ensure that it is compatible with Houdini (NOT reverseable)."""
    name = hou.text.alphaNumeric(name)
    if name[0].isdigit():
        name = '_'+name
    return name


"""
The following dict is used to ensure certain important features are configured properly,
conforming to the recommended implementation in Microsoft's OpenType Spec.
( https://learn.microsoft.com/en-us/typography/opentype/spec/features_ae )
This is important because some parameters should essentially never be surfaced
to the end-user, and others are dependent on per-glyph information coming
from the shaper, so setting them to a uniform value gives unintended results.

The best example of complex feature usage would be in Arabic,
where there are often alternate glyphs for the beginning and end of tones.

Any features not declared in the below dictionary will be disabled by default,
since they are likely designated as being up to the user.

Format:
{ 'FEATURE_NAME', ( DEFAULT_STATE, SHOULD_BE_EXPOSED_TO_USER)}
"""
featureDefaults = {
    'calt':(True, True),
    'clig':(True, True),
    'ccmp':(True, False),
    'cpsp':(True, False), #Capital spacing
    'dist':(True, False), #Distances
    'fina':(True, False), #Terminal forms, likely has conditional activation
    'init':(True, False), #Initial forms, likely has conditional activation
    'falt':(True, False), #Final Glyph on Line Alternates, likely has conditional activation
    'jalt':(True, True), 
    'kern':(True, True),
    'liga':(True, True),
    'locl':(True, False), #Localized forms, likely has conditional activation
    'mark':(True, False), #Mark Positioning
    'mkmk':(True, False), #Mark to Mark Positioning
    'medi':(True, False), #Medial Forms, This is essential to correctly working with Arabic
    'opbd':(True, True),
    'REQD':(True, False), #No idea wtf this one is, but it's present in Avenir Next. Given the name, I'm assuming it's an internal feature which shouldn't be exposed to the user.
    'rclt':(True, False), #Required Contextual Alternates, Useful for better glyph joining behavior, likely context-sensitive
    'rvrn':(True, False),
    'rlig':(True, False),
    'rtlm':(True, False), #Right-to-left Mirrored Forms, likely has conditional activation
    'size':(True, True),
    'valt':(True, True), #Alternate Vertical Metrics, Should be active by default in vertical layout
    'vert':(False, True), # Vertical Alternatess, Should be active by default in vertical layout
    'vkrn':(True, True), #Enable kerning for vertical layout, unlike the other vertical stuff it shouldn't hurt anything to leave on
    'vrt2':(False, True), #Vertical Alternates and Rotation, Should be active by default in vertical layout, otherwise off
    'vrtr':(False, True), #Vertical Alternates for Rotation, Should be applied to applicable characters in vertical text layout
}


SUBFAMILY_ORDER = {
    "Hairline":0,
    "ExtraThin":0,
    "UltraThin":0,
    "Thin":100,
    "ExtraLight":200,
    "UltraLight":200,
    "Light":300,
    "Book":400,
    "Normal":400,
    "Regular":400,
    "Roman":400,
    "Medium":500,
    "SemiBold":600,
    "Demi":600,
    "DemiBold":600,
    "Bold":700,
    "ExtraBold":800,
    "UltraBold":800,
    "Heavy":850,
    "Black":900,
    "ExtraBlack":1000,
    "UltraBlack":1000,
    "Super":1000
}


# This isn't really needed right now, but it could be useful to support the changing of parameter names across multiple asset versions.
PARMNAMING = {
    "1.0" : {
        'font':'file',
        'font_number':'font_collection_number',
        
        'font_family_menu':'font_select_in_family',
        'font_instances':'font_instances'
    },
}


def clamp( value: float, min: float=0, max: float=1):
    """Returns value clamped between min and max."""
    return min if value < min else max if value > max else value


def fit( valin: float, omin: float=0, omax: float=1, nmin: float=0, nmax: float=1):
    """Takes the value in one range and shifts it to the corresponding value in a new range."""
    fac = (clamp(valin,omin,omax) - omin) / (omax - omin)
    return nmin + fac * (nmax - nmin)


class FontParmInfo(NamedTuple):
    path:Path
    number:int
    validfont:bool
    family:str
    name:str
    info:fontFinder.NameInfo
    is_filepath:bool
    is_collection:bool

def interpret_font_parms( targetnode:hou.OpNode, read_collection_fontnumber=True, parm_naming_version="1.0"):
    """Interpret the font parameters for a given Typecaster font node, getting useful information about the font it is currently set to.

    Args:
        targetnode (hou.OpNode): Node to operate on.
        read_collection_fontnumber (bool, optional): Disable if you don't want the current interface's font number to be considered. Defaults to True.
        parm_naming_version (str, optional): Identifier for the parameter naming scheme used for the current node. Defaults to "1.0".

    Returns:
        (FontParmInfo): A named tuple with the font parameter information.
    """
    parmnames = PARMNAMING[parm_naming_version]
    fontparm = targetnode.parm(parmnames['font'])
    fontparmval = fontparm.eval()

    info = fontFinder.name_info(fontparmval)
    fontpath = Path(fontparmval).resolve()
    fontnumber = 0
    fontfamily = None
    fontname = None
    fontparm_is_filepath = True
    font_is_collection = False
    validfont = True
    if fontpath.exists():
        font_is_collection = fontpath.suffix.lower() in fontFinder.COLLECTIONSUFFIXES
        if read_collection_fontnumber and font_is_collection:
            numberparm:hou.Parm = targetnode.parm(parmnames['font_number'])
            if numberparm:
                fontnumber:int = eval(numberparm.evalAsString())
        name_mappings = fontFinder.path_to_name_mappings(fontpath)
        if name_mappings:
            try:
                fontname = name_mappings[fontnumber]
            except KeyError:
                # Didn't have a valid number. Use the first name in the dict instead
                fontname = list(name_mappings.values())[0]
            info = fontFinder.name_info(fontname)
            fontfamily = info.family
    elif info:
        # If the parm is a font name, get the main info from there
        fontparm_is_filepath = False
        fontpath = info.path
        fontnumber = info.number
        fontfamily = info.family
        fontname = fontparmval
    else:
        validfont=False
    finfo = FontParmInfo(fontpath, fontnumber, validfont, fontfamily, fontname, info, fontparm_is_filepath, font_is_collection)
    return finfo


def interpret_font_parms_min( targetnode:hou.OpNode, parm_naming_version="1.0" ) -> tuple[Path,int,bool]:
    """Interpret the font parameters for a given Typecaster font node, but only the minimum amount of information to construct a TTFont object.

    Args:
        targetnode (hou.OpNode): Node to operate on.
        parm_naming_version (str, optional): Identifier for the parameter naming scheme used for the current node. Defaults to "1.0".

    Returns:
        tuple[Path,int,bool]: A tuple with the font parameter information. This is the same as the first three values in a FontParmInfo object.
    """
    parmnames = PARMNAMING[parm_naming_version]
    fontparmval = targetnode.evalParm(parmnames['font'])
    fontpath = Path(fontparmval).resolve()
    fontnumber = 0
    validfont = True
    if fontpath.exists():
        fontnumberparm:hou.Parm = targetnode.parm(parmnames['font_number'])
        if fontnumberparm:
            fontnumber = eval(fontnumberparm.evalAsString())
    else:
        info =fontFinder.name_info(fontparmval)
        if info:
            fontpath = info.path
            fontnumber = info.number
        else:
            validfont = False
    return fontpath, fontnumber, validfont


def get_varaxes_vexops(font_info_string:str):
    """Construct the vexcode needed to read in the varaxes parameters and attributes for a given font.
    This function is only really intended for internal use and has no purpose for the end-user.

    Args:
        font_info_string (str): Font info string from the font_info parameter being used by Typecaster's core. This should be the string representation of interpret_font_parms_min.

    Returns:
        tuple[str,str]: A tuple of strings to be used by parts of Typecaster for interpreting varaxes.
    """
    # While you could argue that this isn't the right module since it doesn't modify the UI, I think it makes the most sense to put it here.
    # While the code itself doesn't depend on interpret_font_parms_min, it's the expected return value being passed to this function.
    font_info_min = eval(font_info_string)
    try:
        fnt = tcf.Font.Cacheable(font_info_min[0],font_info_min[1])
        variation_axes = fnt.font.axes
    except tcf.FontInitFailure:
        # No need to indicate an error here, since typecaster_core will be erroring in the case at the same time
        variation_axes = None
    vexremap  = ''
    vexreader = ''
    if variation_axes:
        for parmname in variation_axes:
            # Get the required values for the current parameter
            minval = variation_axes[parmname].get('minValue')
            maxval = variation_axes[parmname].get('maxValue')
            default = variation_axes[parmname].get('defaultValue')
            default = fit(default, minval, maxval)
            parmname = ensure_compatible_name(parmname)

            # Add a corresponding line for reading in the current axes in vex for per-glyph variation
            vexremap += f"""attribfound += remap_if_found( '{parmname}', {minval}, {maxval}, @ptnum );\n"""
            vexreader += f"""attribfound += read_if_found( '{parmname}', tgt, @ptnum);\n"""
    return vexremap,vexreader


def update_font_parms(node:hou.OpNode=None, triggersrc:str=None, newnumber:int=-1):
    """Update all font-dependent components of the interface. The functionality can be split into two categories:
    1) Features, which are toggleable components of a font that often inform glyph substitutions

    2) Variation Axes, which are the parameters used to control a variable font. While these are internally controlled using
    authored ranges corresponding to typographic standards, it is most often better for these purposes to normalize to 0-1. This way,
    all fonts can be controled using a consistent range of values. Additionally, this also parses a font's available instances, which
    are essentially embedded presets for various weights of a font.
    
    By default this will operate on the current node, although this can be overridden.
    """

    if not node:
        node:hou.OpNode = hou.pwd()
    fontparminfo = interpret_font_parms(node, read_collection_fontnumber= triggersrc=='collection')
    validfont = False
    if fontparminfo.validfont:
        # Do I need to do this any more? Or is fontparminfo.validfont reliable enough.
        try:
            targetfont = tcf.Font.Cacheable(fontparminfo.path, number=fontparminfo.number if newnumber == -1 else newnumber)
            validfont = True
        except tcf.FontInitFailure:
            # No need to indicate an error here, since typecaster_core will be erroring in the case at the same time
            pass

    # Only run if a valid found is found in the target parameter
    if validfont:
        # Basic stuff needed
        fontgoggle = targetfont.font
        ptg:hou.ParmTemplateGroup = node.parmTemplateGroup()

        # Create the menu to switch within font families
        parmname = 'font_select_in_family'
        if triggersrc != 'family':
            if ptg.find(parmname):
                ptg.remove(parmname)
            if fontparminfo.family:
                families = fontFinder.families(fontparminfo.family)
                if families:
                    menuitems = []
                    menulabels = []
                    for fontname in families:
                        finfo = fontFinder.name_info(fontname)
                        if fontparminfo.is_filepath:
                            if fontparminfo.is_collection:
                                menuitems.append(repr((finfo.interface_path, finfo.number)))
                            else:
                                menuitems.append(repr((finfo.interface_path, -1)))
                        else:
                            menuitems.append(repr((fontname, -1)))
                        use_fullname:hou.Parm = node.parm('familymenu_use_full_names')
                        if use_fullname and use_fullname.eval():
                            menulabels.append(fontname)
                        else:
                            menulabels.append(finfo.subfamily)
                    menuitems, menulabels = _sort_family_menu_(menuitems, menulabels)
                    menuitems.insert(0, '')
                    menulabels.insert(0, 'Select Font         ↓')
                    familymenu = hou.StringParmTemplate( parmname, 'Fonts in Family', 1, default_value=menuitems[0],
                                                menu_items=menuitems,
                                                menu_labels=menulabels,
                                                script_callback = "kwargs['node'].hdaModule().set_from_font_family()",
                                                script_callback_language=hou.scriptLanguage.Python,
                                                join_with_next=fontparminfo.is_collection )
                    ptg.insertBefore("reload_parms", familymenu)
        else:
            familypt:hou.ParmTemplate = ptg.find(parmname)
            if familypt and familypt.joinsWithNext() != fontparminfo.is_collection:
                familypt.setJoinWithNext(fontparminfo.is_collection)
                ptg.replace(parmname, familypt)
                
        parmname = 'font_collection_number'
        found = ptg.find(parmname)
        if found:
            ptg.remove(parmname)
        if triggersrc != "collection":
            if fontparminfo.is_collection:
                menuitems, menulabels = _get_collection_menu_(fontparminfo.path)

                # Reset the font number if it is set to something greater than the maximum of the current collection
                # It might make more sense to do this nomatter what so that the behavior is more consistent
                parm: hou.Parm = node.parm(parmname)
                if parm:
                    if parm.eval() >= len(menuitems):
                        parm.set(0)
                
                collectionmenu = hou.MenuParmTemplate( parmname, 'Collection Font',
                            menu_items = menuitems,
                            menu_labels = menulabels,
                            default_value = menuitems.index(min(menuitems)),
                            script_callback = "kwargs['node'].hdaModule().update_font_parms(triggersrc='collection')",
                            script_callback_language=hou.scriptLanguage.Python )
                ptg.insertBefore("reload_parms", collectionmenu)
        elif found:
            ptg.insertBefore("reload_parms", found)

        existing_parms = {}

        # Create all parameters related to variable font axes
        # vexremap = ""
        # vexreader = ""
        realparms = []
        variation_axes = fontgoggle.axes
        if variation_axes:
        
            # Enable the has_varying_parms toggle to enable visibility of the parameter folder
            node.parm('has_varying_parms').set(1)

            varfoldername = "varaxes"
            varfolder = ptg.find(varfoldername)
            if not varfolder:
                varfoldername = varfoldername+'2'
                varfolder = ptg.find(varfoldername)
            existing_parms = { parm.name() : parm for parm in varfolder.parmTemplates()}

            # Create the instance preset menu, remove it if it already existed
            parmname = 'font_instances'
            if ptg.find(parmname):
                ptg.remove(parmname)
            instances = targetfont.instances()
            if instances:
                menuitems = ['',]+list( str(val) for val in instances.values())
                instancemenu = hou.StringParmTemplate( parmname, 'Font Instances', 1, default_value=menuitems[0],
                                            menu_items=menuitems,
                                            menu_labels=['Select Preset         ↓',]+list(instances.keys()),
                                            script_callback = "kwargs['node'].hdaModule().set_from_font_instance()",
                                            script_callback_language=hou.scriptLanguage.Python )
                ptg.insertBefore("varlabels", instancemenu)

            # Main handling of each variation axes
            for parmname in variation_axes:
                # Get the required values for the current parameter
                minval = variation_axes[parmname].get('minValue')
                maxval = variation_axes[parmname].get('maxValue')
                default = variation_axes[parmname].get('defaultValue')
                default = fit(default, minval, maxval)
                parmname = ensure_compatible_name(parmname)
                parmname_real = parmname+'_real'

                # If the axes already exists in the interface, remove it and it's axes_real parameter as well
                if parmname in existing_parms:
                    ptg.remove(parmname)
                    ptg.remove(parmname_real)
                    existing_parms.pop(parmname)
                    existing_parms.pop(parmname_real)

                # Create the pair of parm templates for the current axes and append it to the ptg
                template_norm = hou.FloatParmTemplate(parmname, parmname, 1, min=0, max=1, join_with_next=True, default_value=(default,))
                template_real = hou.FloatParmTemplate(parmname_real, parmname, 1, is_label_hidden=True, min=0, max=1, 
                                            default_expression=(f"""fit01(ch("{parmname}"), {minval}, {maxval})""",),
                                            tags = {'sidefx::slider':'none'}  
                                            )
                realparms.append( parmname_real )
                
                varfolder = ptg.find(varfoldername)
                ptg.appendToFolder( varfolder, template_norm)
                varfolder = ptg.find(varfoldername)
                ptg.appendToFolder( varfolder, template_real)

                # # Add a corresponding line for reading in the current axes in vex for per-glyph variation
                # vex_remapline = f"""attribfound += remap_if_found( '{parmname}', {minval}, {maxval}, @ptnum );"""
                # vexremap += vex_remapline+"\n"
                # vex_readerline = f"""attribfound += read_if_found( '{parmname}', tgt, @ptnum);"""
                # vexreader += vex_readerline+"\n"
        else:
            node.parm('has_varying_parms').set(0)

        # Find all the feature folders and add their already existing parameters
        featfolder_name = "general_features"
        ssfolder_name = "stylistic_sets"
        cvfolder_name = "character_variants"

        targetfolder = ptg.find(featfolder_name)
        if not targetfolder:
            featfolder_name = featfolder_name+'2'
            targetfolder = ptg.find(featfolder_name)
        existing_parms.update({ parm.name() : parm for parm in targetfolder.parmTemplates()})

        targetfolder = ptg.find(ssfolder_name)
        if not targetfolder:
            ssfolder_name = ssfolder_name+'2'
            targetfolder = ptg.find(ssfolder_name)
        existing_parms.update({ parm.name() : parm for parm in targetfolder.parmTemplates()})

        targetfolder = ptg.find(cvfolder_name)
        if not targetfolder:
            cvfolder_name = cvfolder_name+'2'
            targetfolder = ptg.find(cvfolder_name)
        existing_parms.update({ parm.name() : parm for parm in targetfolder.parmTemplates()})

        # Construct all of the font's feature toggles
        combined_features = set(fontgoggle.featuresGPOS) | set(fontgoggle.featuresGSUB)
        add_defaults:hou.Parm = node.parm('ensure_default_font_features')
        if add_defaults and add_defaults.eval():
            # """
            # In some unusual edgecases, I've seen fonts which make use of features which are not listed in either their
            # GSUB or GPOS tables. An example of this would be Futura.ttc (the only one actually), which has ligatures enabled by default,
            # but doesn't list 'liga' as a feature. This is problematic since the parameter won't be exposed to the user by default.
            # """
            combined_features.update( featureDefaults.keys() )

        combined_features = list(combined_features)
        combined_features.sort()
        if combined_features:
            from fontgoggles.misc.opentypeTags import features as featurelookup
            # Add all the features to the interface that are supposed to be user-controlled,
            # separating out Stylistic Sets and Character variants into their own folder
            stylisticsets = []
            general_counter = 0
            cvar_counter = 0
            for featname in combined_features:
                if featname.startswith('ss') and len(featname) == 4:
                    stylisticsets.append(featname)
                else:
                    featureDefault = featureDefaults.get(featname, (False, True))
                    if featureDefault[1]:
                        defval = featureDefault[0]
                        # Remove the parameter if it already exists
                        if featname in existing_parms:
                            ptg.remove(featname)
                            existing_parms.pop(featname)
                        if featname.startswith('cv') and len(featname) == 4:
                            targetfolder = ptg.find(cvfolder_name)
                            # TODO: Is there some way to get character variation names reliably like stylistic sets?
                            # Probably some table in the opentype spec has this info...
                            label = featname
                            cvar_counter += 1
                            do_join = (cvar_counter) % 5 > 0
                        else:
                            targetfolder = ptg.find(featfolder_name)
                            label = featurelookup.get(featname, (featname,))[0]
                            general_counter += 1
                            do_join = (general_counter) % 5 > 0
                        template = hou.ToggleParmTemplate( featname, label, default_value= defval, join_with_next= do_join)
                        ptg.appendToFolder( targetfolder, template)
            if stylisticsets:
                stylisticsets.sort()
                ssNames =fontgoggle.stylisticSetNames
                for i, ssname in enumerate(stylisticsets):
                    if ssname in ssNames:
                        label = f"{ssname}: {ssNames[ssname]}"
                    else:
                        # If a specific name isn't given for the stylistic set, fall back to it's common name
                        label = featurelookup.get(ssname, (ssname,))[0]
                    template = hou.ToggleParmTemplate( ssname, label, join_with_next= (i+1) % 2 > 0)
                    if ssname in existing_parms:
                        ptg.remove(ssname)
                        existing_parms.pop(ssname)
                    targetfolder = ptg.find(ssfolder_name)
                    ptg.appendToFolder( targetfolder, template)

        # Clean up any leftover parameters from previous fonts
        for leftover in existing_parms:
            ptg.remove(leftover)

        # Set the new modified ptg
        node.setParmTemplateGroup(ptg)

        if fontparminfo.is_collection and newnumber != -1:
            fontnumberparm:hou.Parm = node.parm('font_collection_number')
            if fontnumberparm:
                fontnumberparm.set(fontnumberparm.menuItems().index(str(newnumber)))

        # # Set the string referenced for vex attribute handling
        # node.parm('vex_varAxesMapping').set(vexremap)
        # node.parm('vex_varAxesReading').set(vexreader)

        # # Lock the real varaxes parameters, since they really shouldn't be directly modified unless the user is really determined
        # for preal in realparms: node.parm(preal).lock(True)


def swap_font_parms(node:hou.OpNode=None, swap_mode=0, parm_naming_version="1.0"):
    """
    If possible, swap a font path to it's corresponding font name, or swap a font
    name to it's corresponding path

    Args:
        swap_mode (int): By default, this function inverts the current operation,
            but it can also either only convert to paths, or only to names. This 
            is done with the following values:
            - 0: Swap in both directions
            - 1: Swap paths for names
            - 2: Swap names for paths
    """
    if not node:
        node:hou.OpNode = hou.pwd()
    parmnames = PARMNAMING[parm_naming_version]
    fontinfo = interpret_font_parms(node)
    fontparmval = None
    fontnumber = None
    if fontinfo.is_filepath and (swap_mode==0 or swap_mode==1):
        if fontinfo.name:
            # If currently a path with a corresponding name...
            fontparmval = fontinfo.name
            fontnumber = fontinfo.number
        else:
            msg = 'Unable to swap from path to name! This path might not be searched by Typecaster.'
            if hou.isUIAvailable():
                hou.ui.displayMessage(msg, severity=hou.severityType.Warning, title='Typecaster')
            else:
                print(f"<TYPECASTER WARNING> {msg}")
    elif (swap_mode==0 or swap_mode==2):
        # If currently a name...
        fontparmval = fontinfo.info.interface_path
        fontnumber = fontinfo.number
    if fontparmval:
        fontparm = node.parm(parmnames['font'])
        # Contain all operations within the same undos group
        with hou.undos.group("Typecaster update selected font"):
            fontparm.set(fontparmval)
            node.hdaModule().update_font_parms(node=node, newnumber=fontnumber)


def set_from_font_family(node:hou.OpNode=None, parm_naming_version="1.0"):
    """Update the current font node based off of it's font family parameter value

    Args:
        node (hou.OpNode, optional): Node to operate on. If not specified, hou.pwd() will be used.
    """
    if not node:
        node:hou.OpNode = hou.pwd()
    parmnames = PARMNAMING[parm_naming_version]
    familyparm:hou.Parm = node.parm('font_select_in_family')
    # Evaluate as unexpandedString to preserve environment variables
    menuval = eval(familyparm.unexpandedString())
    if menuval:
        node.parm(parmnames['font']).set(menuval[0])
        font_numberparm:hou.Parm = node.parm(parmnames['font_number'])
        if font_numberparm and menuval[1] != -1:
            try:
                font_numberparm.set(font_numberparm.menuItems().index(str(menuval[1])))
            except ValueError:
                pass
        # Contain all operations within the same undos group
        with hou.undos.group("Typecaster update selected font"):
            familyparm.set('')
            node.hdaModule().update_font_parms(triggersrc='family')
        # familyparm.pressButton()


def set_from_font_instance(node:hou.OpNode=None):
    """Update the current font axes using the values contained within the instance parm's menu values.
    
    Args:
        node (hou.OpNode, optional): Node to operate on. If not specified, hou.pwd() will be used.
    """
    if not node:
        node:hou.OpNode = hou.pwd()
    instanceparm = node.parm('font_instances')
    menuval = eval( instanceparm.eval() )
    if menuval:
        for p in menuval:
            # Technically it's possible for the varaxes to use names that aren't permitted as houdini parms.
            # Encoding the parameter name fixes this. (Probably overkill since I've only seen this on one 9-year old font that is clearly incomplete)
            tparm = node.parm(ensure_compatible_name(p))
            if tparm:
                tparm.set(menuval[p])
            else:
                print(f"Couldn't find parameter {p}! Was it deleted?")
        instanceparm.set('')


def font_selection_tree( node:hou.Node=None, parm_naming_version="1.0" ):
    """Create a basic ui tree for font selection. Not a replacement for a proper interface but a nice in-between.
    Depending on the state of the target node, the items will either be font paths or font names.
    
    Args:
        node (hou.Node): The node to operate on.
    """
    if not node:
        node:hou.OpNode = hou.pwd()
    parmnames = PARMNAMING[parm_naming_version]
    parm:hou.Parm = node.parm(parmnames['font'])
    families = fontFinder.families()
    name_info = fontFinder.name_info()
    parminfo = interpret_font_parms( node, read_collection_fontnumber=True, parm_naming_version="1.0")
    items_are_paths = False
    if parminfo.is_filepath and parminfo.info:
        items_are_paths = True

    choices = []
    to_parmval = {}
    for fam in families:
        choices.append(fam)
        for fnt in families[fam]:
            info:fontFinder.NameInfo = name_info[fnt]
            tags = info.tags
            choice=''
            if 'variable' in tags and tags['variable'] is True:
                choice = " ||Variable"
            source =  tags.get('source',None)
            if source:
                choice += f" ||Source:{source}"

            choice = fam+"/"+fnt+choice
            choices.append(choice)
            if items_are_paths:
                fnt = info.interface_path
            to_parmval[choice] = fnt

    def show_ui(**kwargs):
        selection = hou.ui.selectFromTree( choices, exclusive=True, title="Make Font Selection", **kwargs)
        return selection[0] if selection else None

    msg = "Please select a font from within the listed font families."
    val = show_ui(message=msg)
    while val in families:
        val = show_ui(message=msg+"\nPlease select a specific font and not a family.")

    if val:
        name = to_parmval[val]
        parm.set(name)
        parm.pressButton()


def font_selection_dropdown( node:hou.OpNode=None):
    """Generate a font selection dropdown, which is essentially an improved version of the native Font node's dropdown menu.
    Depending on the state of the target node, the items will either be font paths or font names.

    Args:
        node (hou.OpNode, optional): The node that the menu is for. If not specified, hou.pwd() will be used.

    Returns:
        (list): List of menu items and labels combined together.
    """
    if not node:
        node:hou.OpNode = hou.pwd()
    families = fontFinder.families()  
    parminfo = interpret_font_parms( node, read_collection_fontnumber=True, parm_naming_version="1.0")
    items_are_paths = False
    if parminfo.is_filepath and parminfo.info:
        items_are_paths = True
        name_info = fontFinder.name_info()

    menu = []
    for fam in sorted(families):
        menu.extend( ("_separator_", "_separator") )
        fam = _sort_family_(families[fam])
        if items_are_paths:
            for name in fam:
                menu.extend( (name_info[name].interface_path, name) )
        else:
            for name in fam:
                menu.extend( (name, name) )
    return menu


"""
-----------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------
Semi-internal functions for building specific subcomponents of the interface.

These are not expected to be called directly in the interface or by the end user

"""


def _get_collection_menu_(fontpath:Path) -> tuple[list[str],list[str]]:
    """
    Using a path to a font collection file, output a pair of menu items and
    labels for specifying a font number within a collection.
    
    Args:
        fontpath(Path): Pathlib Path to a font collection file.
    """
    fontpath = fontpath.resolve()
    menu_items = []
    menu_labels = []
    subfamily_names = []
    name_mappings = fontFinder.path_to_name_mappings(fontpath)
    if name_mappings:
        infos = fontFinder.name_info()
        for number in name_mappings:
            name = name_mappings[number]
            info:fontFinder.NameInfo = infos[name]
            subfamily_names.append(info.subfamily)
            menu_items.append( str(info.number) )
            menu_labels.append(name)
    else:
        collection = TTCollection(fontpath)
        for number, ttfont in enumerate(collection.fonts):
            name, family, subfamily = fontFinder.get_best_names(ttfont)
            subfamily_names.append(subfamily)
            menu_items.append( str(number) )
            menu_labels.append(name)  
    menu_items, menu_labels =_sort_family_menu_(menu_items=menu_items,menu_labels=menu_labels,subfamily_names=subfamily_names)
    return menu_items, menu_labels


def _get_subfamily_priority_( subname:str)->int:
    """Get the priority number of the closest match to the input
    subfamily name.

    Args:
        subname (str): Subfamily name to search against. This is converted to lowercase and
            has all of it's spaces removed before comparison.

    Returns:
        int: Priority number for the subfamily.
    """
    subname = subname.lower().replace(" ","")
    matchorder = []
    for tgt in SUBFAMILY_ORDER:
        match = re.match(f".*{tgt.lower()}.*", subname)
        sz = 0
        if match:
            span = match.span()
            sz = span[1]-span[0]
        matchorder.append( (sz, tgt) )
    closestmatch = sorted(matchorder)[-1][1]
    return SUBFAMILY_ORDER[closestmatch]


def _get_weight_priority_from_info_(info:fontFinder.NameInfo):
    return info.weight + info.italic + (info.width*10000) if info.weight != -1 else _get_subfamily_priority_(info.subfamily)


def _sort_family_( family_list:list[str]):
    """Sort a list of subfamilies for a given font.

    Args:
        family_list (list[str]): List of subfamilies

    Returns:
        list[str]: Sorted version of family_list
    """
    d_name_info: dict[str,fontFinder.NameInfo] = fontFinder.name_info()
    # return sorted( family_list, key=lambda item: _get_subfamily_priority_( d_name_info[item].subfamily ) )
    return sorted( family_list, key=lambda item: _get_weight_priority_from_info_(d_name_info[item]))


def _sort_family_menu_( menu_items:list[str], menu_labels:list[str], subfamily_names:list[str]=None) -> tuple[list[str],list[str]]:
    """
    Sort an already-created pair of menu_items and menu_labels. This sorts by the menu_labels
    or by a separate subfamily_names list,
    which are expected to have a standard name for font weights in their name.
    
    For example:
        [ "Heavy", "Thin", "Book"] would be sorted to [ "Thin", "Book", "Heavy"],with the menu items sorted in the same order.

    Args:
        menu_items(list[str]): A list of parameter values you will be replacing from the menu. This is NOT used for sorting.
        menu_labels(list[str]): A list of font subfamilies. This is the list used for sorting.
        sufamily_names(list[str], optional): A list of font subfamilies. This is used instead of menu_labels if it is specified.
    Returns:
        tuple[list[str],list[str]]: Sorted versions of menu_items and menu_labels
    """
    if subfamily_names:
        paired_lists = sorted(zip(menu_items, menu_labels, subfamily_names), key=lambda item: _get_subfamily_priority_(item[2]) )
        menu_items, menu_labels, subfamily_names = zip(*paired_lists)
    else:
        paired_lists = sorted(zip(menu_items, menu_labels), key=lambda item: _get_subfamily_priority_(item[1]) )
        menu_items, menu_labels = zip(*paired_lists)
    return list(menu_items), list(menu_labels)


def _get_family_menu_( font_parm_info: FontParmInfo) -> tuple[list[str],list[str]]:
    """Using a family name, output a pair of menu items and labels for chosing a different font within the same family.

    Args:
        font_parm_info (FontparmInfo): Information about the font parameters for a node.

    Returns:
        tuple[list[str],list[str]]: Returns a tuple of both a menu_items list and a menu_labels list.
    """
    menuitems = []
    menulabels = []
    if font_parm_info.family:
        in_family = fontFinder.families(font_parm_info.family)
        if in_family:
            for fontname in in_family:
                finfo = fontFinder.name_info(fontname)
                if font_parm_info.is_filepath:
                    menuitems.append(finfo.interface_path)
                else:
                    menuitems.append(fontname)
                menulabels.append(finfo.subfamily)
            menuitems, menulabels = _sort_family_menu_(menuitems, menulabels)
    return menuitems, menulabels


"""
-----------------------------------------------------------------------------------------------------------------------------
-----------------------------------------------------------------------------------------------------------------------------
Standalone QT UIs for more complex interfaces

"""


class FontSelector(QtWidgets.QDialog):
    def __init__(self, parent, fontnode:hou.OpNode=None):
        if not fontnode:
            self.fontnode:hou.OpNode = hou.pwd()
        else:
            self.fontnode = fontnode
        self.fontparm:hou.Parm = self.fontnode.parm(PARMNAMING["1.0"]["font"])
        if not self.fontparm:
            raise Exception("Is this being run in the appropriate context or node?")
        self.fontparminfo = interpret_font_parms(self.fontnode, read_collection_fontnumber=True)

        # fontfinder info
        self.name_info = fontFinder.name_info()
        self.families = fontFinder.families()
        # self.weights = SUBFAMILY_ORDER.keys()
        self.source_tags = set()
        for k in self.name_info:
            src = self.name_info[k].tags.get('source',None)
            if src:
                self.source_tags.add(src)

        super(FontSelector, self).__init__(parent)

        self.added_fonts = {}
        self.font_preview_inline = False
        self.font_preview_standalone = False

        self.setWindowTitle(f"Font Selector ({self.fontnode.name()})")
        self.buildui()
        self.refresh()

    def buildui(self):
        main_layout = QtWidgets.QVBoxLayout()
        btn_layout = QtWidgets.QHBoxLayout()

        # Selection tree
        self.tree_widget = QtWidgets.QTreeWidget()
        self.tree_widget.setColumnCount(4)
        self.tree_widget.setHeaderLabels(["Fonts", "Weight", "Source", "Is Variable", "Sample Text"])
        self.tree_widget.setColumnHidden(4,1)
        # self.tree_widget.setSortingEnabled(True)
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.setWhatsThis("Font selection. Double-click on a font to apply without exiting the browser, press enter to apply a font and exit, or use the buttons at the bottom of the window.")

        main_layout.addWidget(self.tree_widget, stretch=2)
        self.tree_widget.itemSelectionChanged.connect(self.tree_callback)
        self.tree_widget.itemDoubleClicked.connect(self.apply)

        # Init layout components
        filtergrid = QtWidgets.QGridLayout()
        main_layout.addLayout(filtergrid)
        previewgrid = QtWidgets.QGridLayout()
        main_layout.addLayout(previewgrid)
        textbox = QtWidgets.QHBoxLayout()
        main_layout.addLayout(textbox)

        # Font search with completer
        font_search_label = QtWidgets.QLabel('Font Wildcard Search: ')
        self.font_search = QtWidgets.QLineEdit()
        filtergrid.addWidget(font_search_label, 0, 0)
        filtergrid.addWidget(self.font_search, 0, 1)
        completer = QtWidgets.QCompleter(self.families.keys())
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.font_search.setCompleter(completer)
        self.font_search.editingFinished.connect(self.apply_filters)
        self.font_search.setWhatsThis("Search for fonts using Unix shell-style wildcards.")

        # # Filter weights
        # filter_weight_label = QtWidgets.QLabel('Weight: ')
        # self.filter_weight = QtWidgets.QLineEdit()
        # form.addWidget(filter_weight_label, 0, 2)
        # form.addWidget(self.filter_weight, 0, 3)
        # weightcompleter = QtWidgets.QCompleter(self.weights)
        # weightcompleter.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # self.filter_weight.setCompleter(weightcompleter)
        # self.filter_weight.editingFinished.connect(self.apply_filters)
        # # filter_weight_label.setHidden(True)
        # # self.filter_weight.setHidden(True)

        # Filter by search source
        filter_source_label = QtWidgets.QLabel('Source: ')
        self.filter_source = QtWidgets.QComboBox()
        self.filter_source.addItem('Any')
        for i in self.source_tags:
            self.filter_source.addItem(i)
        filtergrid.addWidget(filter_source_label, 0, 4)
        filtergrid.addWidget(self.filter_source, 0, 5)
        self.filter_source.currentIndexChanged.connect(self.apply_filters)
        self.filter_source.setWhatsThis("Filter specific font sources.")

        # Filter variable fonts
        filter_variable_label = QtWidgets.QLabel('Variable: ')
        self.filter_variable = QtWidgets.QComboBox()
        for i in ['Any','Yes','No']:
            self.filter_variable.addItem(i)
        filtergrid.addWidget(filter_variable_label, 0, 6)
        filtergrid.addWidget(self.filter_variable, 0, 7)
        self.filter_variable.currentIndexChanged.connect(self.apply_filters)
        self.filter_variable.setWhatsThis("Choose what kinds of fonts to show between variable, static, and all.")

        # Font preview menu
        font_preview_label = QtWidgets.QLabel('Preview font: ')
        self.font_preview = QtWidgets.QComboBox()
        for i in ['No','In-line','In-line & Text Box']:
            self.font_preview.addItem(i)
        previewgrid.addWidget(font_preview_label, 1, 0)
        previewgrid.addWidget(self.font_preview, 1, 1)
        self.font_preview.currentIndexChanged.connect(self.update_font_preview)
        self.font_preview.setWhatsThis('Change this to preview the fonts before you apply them. "Inline" adds a preview to each item in the selection menu, and "Text Box" adds a editable text box which uses the currently highlighted font.')

        # Editable text preview for current font selection
        self.font_preview_label = QtWidgets.QLabel('Sample Text: ')
        previewgrid.addWidget(self.font_preview_label, 2, 0)
        self.font_preview_text = QtWidgets.QPlainTextEdit('The quick brown fox jumps over the lazy dog.\n0123456789')
        textbox.addWidget(self.font_preview_text)
        f = self.font_preview_text.font()
        self.preview_font_base_pixelsize = f.pixelSize()
        f.setPixelSize(self.preview_font_base_pixelsize*2)
        self.font_preview_text.setFont(f)

        # Size slider for text preview
        self.sizeslider = QtWidgets.QSlider(Qt.Orientation.Vertical)
        textbox.addWidget(self.sizeslider)
        self.sizeslider.valueChanged.connect(self.update_testsize)
        self.textslider_min = 0
        self.textslider_max = 8
        self.sizeslider.setValue(fit(2,self.textslider_min,self.textslider_max,self.sizeslider.minimum(),self.sizeslider.maximum()))
        self.sizeslider.setWhatsThis(f"Chose the scale of the test text, relative to the rest of the UI size. Between {self.textslider_min}x and {self.textslider_max}x.")

        # Set as path toggle
        self.set_as_path_widget = QtWidgets.QCheckBox('Set as path')
        if self.fontparm.isAtDefault(compare_temporary_defaults=False):
            use_path = False
        else:
            use_path = bool(self.fontparminfo.is_filepath and self.fontparminfo.info)
        self.set_as_path_widget.setChecked(use_path)
        main_layout.addWidget(self.set_as_path_widget)
        self.set_as_path_widget.setWhatsThis('When enabled, apply the selected font as an actual path. When disabled, use the font name.')

        # add apply and cancel
        self.apply_btn = QtWidgets.QPushButton('Apply')
        self.apply_btn_keep = QtWidgets.QPushButton('Apply (Keep Open)')
        close_btn = QtWidgets.QPushButton('Close')
        main_layout.addLayout(btn_layout)
        btn_layout.addWidget(self.apply_btn)
        btn_layout.addWidget(self.apply_btn_keep)
        btn_layout.addWidget(close_btn)
        self.setLayout(main_layout)
        self.apply_btn.clicked.connect(self.apply_close)
        self.apply_btn_keep.clicked.connect(self.apply)
        close_btn.clicked.connect(self.close)
        # Disable apply by default
        self.disableApply()

    def tree_callback(self):
        items = self.tree_widget.selectedItems()
        if items and items[0].parent():
            # Only enable font application if the item has a parent,
            # ensuring that it is an actual font and not a family name
            self.enableApply()
            if self.font_preview_standalone:
                # Set the widget's font
                info = self.name_info[items[0].text(0)]
                qfnt = self.font_preview_text.font()
                if info.path not in self.added_fonts:
                    font_id = QtGui.QFontDatabase.addApplicationFont(str(info.path))
                    self.added_fonts[info.path] = font_id
                qfnt.setFamily(info.family)
                qfnt.setStyleName(info.subfamily)
                qfnt.setStyleStrategy(QtGui.QFont.NoFontMerging)
                self.font_preview_text.setFont(qfnt)
        else:
            self.disableApply()

    def update_testsize(self,val): 
        sz = self.preview_font_base_pixelsize*fit(val,self.sizeslider.minimum(),self.sizeslider.maximum(),self.textslider_min,self.textslider_max)
        f = self.font_preview_text.font()
        f.setPixelSize(sz)
        self.font_preview_text.setFont(f)

    def enableApply(self):
        self.apply_btn.setEnabled(True)
        self.apply_btn_keep.setEnabled(True)

    def disableApply(self):
        self.apply_btn.setEnabled(False)
        self.apply_btn_keep.setEnabled(False)

    def apply_filters(self):
        """Triggered when a filter is modified and causes an update of the items in the font tree."""
        searchterm = self.font_search.text()
        sourcefilter = None if self.filter_source.currentIndex() == 0 else self.filter_source.currentText()
        varfilter = self.filter_variable.currentIndex()
        self.update_font_tree(searchterm, sourcefilter, varfilter)

    def update_font_tree(self, fontfilter:str=None, sourcefilter:str=None, varfilter:int=0):
        """Update the font selection tree.

        Args:
            fontfilter (str, optional): Filter to apply to font names when building the tree. Defaults to None.
            sourcefilter (str, optional): Source name to filter using fontFinder.NameInfo source tags. Defaults to None.
            varfilter (int, optional): Filter based off of if a font is variable. Defaults to 0.
        """
        self.tree_widget.clear()
        items = []
        
        run_filters=False
        if fontfilter or sourcefilter or varfilter != 0:
            run_filters = True
        for famname in sorted(self.families):
            item = QtWidgets.QTreeWidgetItem([famname])
            # item.setFlags((item.flags() & ~Qt.ItemFlag.ItemIsSelectable))
            add_fam = False
            for fnt in _sort_family_(self.families[famname]):
                info = self.name_info[fnt]
                if run_filters:
                    # I'm not completely happy with using fnmatch as the main 
                    # searcher matcher for this, but wildcard search is super useful
                    if fontfilter and not fnmatch(fnt, fontfilter):
                        continue
                    if varfilter > 0:
                        if varfilter == 1 and info.tags.get('variable',False) is False:
                            continue
                        elif varfilter == 2 and info.tags.get('variable',False) is True:
                            continue
                    if sourcefilter:
                        if info.tags.get('source', None) != sourcefilter:
                            continue
                add_fam = True
                var = 'Yes' if 'variable' in info.tags and info.tags['variable'] is True else 'No'
                src =  info.tags.get('source','')
                subitem = QtWidgets.QTreeWidgetItem([fnt, info.subfamily, src, var, 'The quick brown fox jumps over the lazy dog.'])
                if self.font_preview_inline:
                    self._set_subitem_font_(subitem,info)
                
                item.addChild(subitem)
            if add_fam:
                items.append(item)
        self.tree_widget.addTopLevelItems(items)
        self.tree_widget.expandAll()
        self.tree_widget.resizeColumnToContents(0)

    def update_font_preview(self):
        val = self.font_preview.currentIndex()
        self.font_preview_inline = val > 0
        self.font_preview_standalone = val > 1

        self.font_preview_label.setHidden(1 - self.font_preview_standalone)
        self.font_preview_text.setHidden(1 - self.font_preview_standalone)
        self.sizeslider.setHidden(1 - self.font_preview_standalone)
        if self.font_preview_standalone:
            self.tree_callback()
        if self.font_preview_inline:
            for i in range(self.tree_widget.topLevelItemCount()):
                item = self.tree_widget.topLevelItem(i)
                for j in range(item.childCount()):
                    subitem = item.child(j)
                    self._set_subitem_font_(subitem, self.name_info[subitem.text(0)])
            self.tree_widget.setColumnHidden(4,0)
        else:
            self.tree_widget.setColumnHidden(4,1)

    def _set_subitem_font_(self, subitem:QtWidgets.QTreeWidgetItem, info:fontFinder.NameInfo=None):
        qfnt = subitem.font(0)
        if info.path not in self.added_fonts:
            font_id = QtGui.QFontDatabase.addApplicationFont(str(info.path))
            self.added_fonts[info.path] = font_id
        qfnt.setFamily(info.family)
        qfnt.setStyleName(info.subfamily)
        qfnt.setStyleStrategy(QtGui.QFont.NoFontMerging)
        subitem.setFont(4, qfnt)

    def apply(self):
        """Apply the currently selected font to the font node."""
        native_font = self.fontnode.type().name() == "font"
        items = self.tree_widget.selectedItems()
        if items:
            item = items[0]
            if item.parent():
                fontname = item.text(0)
                info = self.name_info.get(fontname,None)
                if info:
                    as_path = self.set_as_path_widget.isChecked()
                    if as_path:
                        fontname = info.interface_path

                    if native_font:
                        if native_font and as_path and info.number > 0:
                            val = QtWidgets.QMessageBox.warning(
                                self,
                                'Problem with applying font!', 
                                'You have selected a font that is a part of a collection, which is only compatible with Typecaster and not the native font node. Applying will likely result in the wrong font being used.',
                                QtWidgets.QMessageBox.Apply | QtWidgets.QMessageBox.Cancel
                            )
                            if val == QtWidgets.QMessageBox.StandardButton.Apply:
                                self.fontparm.set(fontname)
                        else:
                            self.fontparm.set(fontname)
                    else:
                        # Contain all operations within the same undos group
                        with hou.undos.group("Typecaster update selected font"):
                            self.fontparm.set(fontname)
                            update_font_parms(self.fontnode, newnumber=info.number)

    def apply_close(self):
        self.apply()
        self.close()

    def refresh(self):
        self.update_font_tree()
        self.update_font_preview()

        self.show()
        self.raise_()
