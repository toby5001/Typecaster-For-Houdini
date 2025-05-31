import hou, re
from typing import NamedTuple
from pathlib import Path
from typecaster import fontFinder
from typecaster import font as tcf
from fontTools.ttLib import TTCollection


# This is kinda overkil to set as a standalone variable, but this is what ensures that varaxes are always houdini-readable
ensure_compatible_name = hou.text.variableName


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


__SUBFAMILY_ORDER__ = [
    "hairline",
    "extralight",
    "ultralight",
    "ultrathin",
    "thin",
    "light",
    "regular",
    "roman",
    "normal",
    "book",
    "medium",
    "semibold",
    "demibold",
    "bold",
    "extrabold",
    "ultrabold",
    "heavy",
    "black",
    "extrablack",
]
SUBFAMILY_ORDER = {}
for i, sf in enumerate(__SUBFAMILY_ORDER__):
    SUBFAMILY_ORDER[sf] = i
del __SUBFAMILY_ORDER__


# This isn't really needed right now, but if I ever end up separating out some of these functions to an external file,
# it could be useful to support the changing of parameter names across multiple asset versions.
PARMNAMING = {
    "1.0" : {
        'font':'font',
        'font_number':'font_collection_number'
    },
}


def fit( valin: float, omin: float=0, omax: float=1, nmin: float=0, nmax: float=1):
    """Takes the value in one range and shifts it to the corresponding value in a new range."""
    fac = (valin - omin) / (omax - omin)
    return nmin + fac * (nmax - nmin)


class FontParmInfo(NamedTuple):
    path:Path
    number:int
    family:str
    name:str
    info:fontFinder.NameInfo
    is_filepath:bool
    is_collection:bool
    validfont:bool


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
                fontnumber:int = numberparm.eval()
        names = fontFinder.path_to_names(fontpath)
        if names:
            fontname = names[fontnumber]
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
    finfo = FontParmInfo(fontpath, fontnumber, fontfamily, fontname, info, fontparm_is_filepath, font_is_collection, validfont)
    return finfo

def interpret_font_parms_min( targetnode:hou.OpNode, parm_naming_version="1.0" ) -> tuple[Path,int,bool]:
    """Interpret the font parameters for a given Typecaster font node, but only the minimum amount of information to construct a TTFont object.

    Args:
        targetnode (hou.OpNode): Node to operate on.
        parm_naming_version (str, optional): Identifier for the parameter naming scheme used for the current node. Defaults to "1.0".

    Returns:
        tuple[Path,int,bool]: A tuple with the font parameter information.
    """
    parmnames = PARMNAMING[parm_naming_version]
    fontparmval = targetnode.evalParm(parmnames['font'])
    fontpath = Path(fontparmval).resolve()
    fontnumber = 0
    validfont = True
    if fontpath.exists():
        fontnumberparm:hou.Parm = targetnode.parm(parmnames['font_number'])
        if fontnumberparm:
            fontnumber = fontnumberparm.eval()
    else:
        info =fontFinder.name_info(fontparmval)
        if info:
            fontpath = info.path
            fontnumber = info.number
        else:
            validfont = False
    return fontpath, fontnumber, validfont

def update_font_parms(node:hou.OpNode=None, triggersrc:str=None):
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
        try:
            targetfont = tcf.Font.Cacheable(fontparminfo.path, number=fontparminfo.number)
            validfont = True
        except tcf.FontNotFoundException:
            # No need to indicate an error here, since typecaster_core will be erroring in the case at the same time
            pass

    # Only run if a valid found is found in the target parameter
    if validfont:
        # Basic stuff needed
        fontgoggle = targetfont.font
        ptg = node.parmTemplateGroup()

        # Create the menu to switch within font families
        if triggersrc != 'family':
            parmname = 'font_select_in_family'
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
                            menuitems.append(finfo.interface_path)
                        else:
                            menuitems.append(fontname)
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
                    
                collectionmenu = hou.IntParmTemplate( parmname, 'Collection Font', 1,
                            menu_items = menuitems,
                            menu_labels = menulabels,
                            script_callback = "kwargs['node'].hdaModule().update_font_parms(triggersrc='collection')",
                            script_callback_language=hou.scriptLanguage.Python )
                ptg.insertBefore("reload_parms", collectionmenu)
        elif found:
            ptg.insertBefore("reload_parms", found)

        existing_parms = {}

        # Create all parameters related to variable font axes
        vexremap = ""
        vexreader = ""
        realparms = []
        variation_axes = fontgoggle.axes
        if variation_axes:
        
            # Enable the has_varying_parms toggle to enable visibility of the parameter folder
            node.parm('has_varying_parms').set(1)

            varfoldername = "varaxes"
            varfolder = ptg.find(varfoldername)
            if not varfolder: varfoldername = varfoldername+'2'; varfolder = ptg.find(varfoldername)
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

                # Add a corresponding line for reading in the current axes in vex for per-glyph variation
                vex_remapline = f"""attribfound += remap_if_found( '{parmname}', {minval}, {maxval}, @ptnum );"""
                vexremap += vex_remapline+"\n"
                vex_readerline = f"""attribfound += read_if_found( '{parmname}', tgt, @ptnum);"""
                vexreader += vex_readerline+"\n"
        else:
            node.parm('has_varying_parms').set(0)

        # Find all the feature folders and add their already existing parameters
        featfolder_name = "general_features"; ssfolder_name = "stylistic_sets"; cvfolder_name = "character_variants"

        targetfolder = ptg.find(featfolder_name)
        if not targetfolder: featfolder_name = featfolder_name+'2'; targetfolder = ptg.find(featfolder_name)
        existing_parms |= { parm.name() : parm for parm in targetfolder.parmTemplates()}

        targetfolder = ptg.find(ssfolder_name)
        if not targetfolder: ssfolder_name = ssfolder_name+'2'; targetfolder = ptg.find(ssfolder_name)
        existing_parms |= { parm.name() : parm for parm in targetfolder.parmTemplates()}

        targetfolder = ptg.find(cvfolder_name)
        if not targetfolder: cvfolder_name = cvfolder_name+'2'; targetfolder = ptg.find(cvfolder_name)
        existing_parms |= { parm.name() : parm for parm in targetfolder.parmTemplates()}

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
            general_counter = 0; cvar_counter = 0
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

        # Set the string referenced for vex attribute handling
        node.parm('vex_varAxesMapping').set(vexremap)
        node.parm('vex_varAxesReading').set(vexreader)

        # # Lock the real varaxes parameters, since they really shouldn't be directly modified unless the user is really determined
        # for preal in realparms: node.parm(preal).lock(True)


def swap_font_parms(node:hou.OpNode=None, swap_mode=0, parm_naming_version="1.0"):
    """
    If possible, swap a font path to it's corresponding font name, or swap a font name to it's corresponding path

    Args:
        swap_mode (int): By default, this function inverts the current operation, but it can also either only convert to paths, or only to names. This is done with the following values:
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
    elif (swap_mode==0 or swap_mode==2):
        # If currently a name...
        fontparmval = fontinfo.info.interface_path
        fontnumber = fontinfo.number
    if fontparmval:
        fontparm = node.parm(parmnames['font'])
        fontparm.set(fontparmval)
        node.hdaModule().update_font_parms(node=node)

        numberparm = node.parm(parmnames['font_number'])
        if fontnumber and numberparm:
            numberparm.set(fontnumber)
            node.hdaModule().update_font_parms(node=node, triggersrc='collection')


def set_from_font_family(node:hou.OpNode=None):
    """Update the current font node based off of it's font family parameter value

    Args:
        node (hou.OpNode, optional): Node to operate on. If not specified, hou.pwd() will be used.
    """
    if not node:
        node:hou.OpNode = hou.pwd()
    familyparm:hou.Parm = node.parm('font_select_in_family')
    # menuval = familyparm.eval()
    menuval = familyparm.unexpandedString()
    if menuval:
        node.parm('font').set(menuval)
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


def font_selection_tree( parm:hou.Parm ):
    """Create a basic ui tree for font selection. Not a replacement for a proper interface but a nice in-between.
    Depending on the state of the target node, the items will either be font paths or font names.
    
    Args:
        parm (hou.Parm): The font parameter to set based off of the selection tree.
    """
    families = fontFinder.families()
    name_info = fontFinder.name_info()
    parminfo = interpret_font_parms( parm.node(), read_collection_fontnumber=True, parm_naming_version="1.0")
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
                choice = " || Variable"
            source =  tags.get('source',None)
            if source:
                choice += f" || Source:{source}"

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
    names = fontFinder.path_to_names(fontpath)
    if names:
        infos = fontFinder.name_info()
        for name in names:
            info = infos[name]
            menu_items.append( str(info.number) )
            menu_labels.append(name)
    else:
        collection = TTCollection(fontpath)
        for number, ttfont in enumerate(collection.fonts):
            name = fontFinder.get_best_names(ttfont)[0]
            menu_items.append( str(number) )
            menu_labels.append(name)
    
    paired_lists = sorted(zip(menu_items, menu_labels))
    menu_items, menu_labels = zip(*paired_lists)
    return menu_items, menu_labels

def _get_subfamily_priority_( subname:str)->int:
    """Get the priority number of the closest match to the input
    subfamily name.

    Args:
        subname (str): Subfamily name to search against. This is converted to lowercase and has all of it's spaces removed before comparison.

    Returns:
        int: Priority number for the subfamily.
    """
    subname = subname.lower().replace(" ","")
    matchorder = []
    for tgt in SUBFAMILY_ORDER:
        match = re.match(f".*{tgt}.*", subname)
        sz = 0
        if match:
            span = match.span()
            sz = span[1]-span[0]
        matchorder.append( (sz, tgt) )
    closestmatch = sorted(matchorder)[-1][1]
    return SUBFAMILY_ORDER[closestmatch]


def _sort_family_( family_list:list[str]):
    """Sort a list of subfamilies for a given font.

    Args:
        family_list (list[str]): List of subfamilies

    Returns:
        list[str]: Sorted version of family_list
    """
    d_name_info: dict[fontFinder.NameInfo] = fontFinder.name_info()
    return sorted( family_list, key=lambda item: _get_subfamily_priority_( d_name_info[item].subfamily ) )


def _sort_family_menu_( menu_items:list[str], menu_labels:list[str]) -> tuple[list[str],list[str]]:
    """
    Sort an already-created pair of menu_items and menu_labels. This sorts by the menu_labels,
    which are expected to have a standard name for font weights in their name.
    
    For example:
        [ "Heavy", "Thin", "Book"] would be sorted to [ "Thin", "Book", "Heavy"],with the menu items sorted in the same order.

    Args:
        menu_items(list[str]): A list of parameter values you will be replacing from the menu. This is NOT used for sorting.
        menu_labels(list[str]): A list of font subfamilies. This is the list used for sorting.
    """
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