"""

Submodule for Typecaster's core.
There's basically no reason to use this submodule outside of the Typecaster::typecaster_font HDA.

"""

from __future__ import annotations
import hou
from pathlib import Path, WindowsPath, PosixPath
from pathops import Path as PathopsPath

from typecaster import font as tcf
from typecaster.houdiniPen import HoudiniCubicPen, HoudiniQuadraticPen
from typecaster.bidi_segmentation import line_to_run_segments
# import cProfile


# pt_attribs = {'skeltype' : [], 
#               'gsz' : [],
#               'ids' : [],
#               'gshift' : []
# }

# def increment_point_attribs(skeltype:str="", gsz=[], ids=[], gshift=(0.,0.) ):
#     pt_attribs['skeltype'].append(skeltype)
#     pt_attribs['gsz'].append(gsz)
#     pt_attribs['ids'].append(ids)
#     pt_attribs['gshift'].append(gshift)
    
# def createPoint_delayedAttribs(skeltype:str="", gsz=[], ids=[], gshift=(0.,0.) ):
#     increment_point_attribs(gshift=gshift,gsz=gsz,ids=ids,skeltype=skeltype)
#     return geo.createPoint()

# def dump_point_attribs():
#     print( len(geo.points()) )
#     print( len(tuple(pt_attribs['skeltype'])) )
#     geo.setPointStringAttribValues('skeltype', tuple(pt_attribs['skeltype']) )
#     geo.setPointIntAttribValues('gsz', tuple(pt_attribs['gsz']) )
#     geo.setPointIntAttribValues('ids', tuple(pt_attribs['ids']) )
#     geo.setPointFloatAttribValues('gshift', tuple(pt_attribs['gshift']) )


def output_geo_fast( interfacenode:hou.Node, node:hou.OpNode, geo:hou.Geometry):
    """Main operation for taking a Typecaster font interface and outputting 
    both a series of glyph control points and a skeleton for layout and positioning.

    Args:
        interfacenode (hou.Node): The node which has all of the standard parameters to drive typecaster.
        node (hou.OpNode): The actual python node which Typecaster core is run from.
        geo (hou.Geometry): Geostream to write to.

    Raises:
        hou.NodeError: Raised when there are expected and common issues with running Typecaster, like an invalid font path.
        NotImplementedError: Raised if an edgecase is encountered that wasn't expected to be hit. If possible, please report the font and parameter settings that were being used in a bug report if you are not the author.

    """
        
    """

    The goal of this function is to allow for as much of the processing to be handled by Houdini as is possible.

    This outputs two different things:
        1) A skeleton with the correct connectivity ordering and glyph information. No positioning is done in Python,
        with everything being done in Houdini. This allows for all positioning operations to not cause a recook
        of glyphs, dramatically increasing responsiveness.
        
        2) A point corresponding to each individual closed bezier needed for all of the glyphs in the string.
        Each point contains a float array of 2D positions of each point in the bezier path ordered as
        [x1, y1, x2, y2, x3, y3, ...]

        Each point is then connected as a polyline to all other points within the same glyph. In Houdini,
        this allows for everything to be run through a For-Each Primitive block, separating each glyph to it's own
        multithreaded operation without having to select it in a separate operation. This enables hole operations 
        to be run at the same time.

    """
    
    """
    NOTE: This issue seems to have gone away, but since I don't recall changing anything that would have done that,
    I'm keeping the note here for now.
    FIXME: ABSOLUTELY INSANE IMPLEMENTATION ALERT

    Ok I completely hate this, but the draw_glyph_with_pen() function runs literally like 10x faster or more
    when within a profiler. This makes absolutely no logical sense, but since uharfbuzz is compiled I can't
    really investigate the function any further.

    There's a slight performance hit for running with the profiler most likely, but it's nearly nothing
    in comparison to the hit when the profiler disabled. This goes against literally everything I know
    but I can't deny the performance difference so I guess I've got to leave this in for now.

    To elaborate about what's causing this difference, it appears to be anything in relation to retreiving the
    glyph beziers using uharfbuzz. I tried 2 different methods for gettting the curve information,
    each with their own performance characteristics. Both of them make use of HoudiniPen, which is my
    general class for either HoudiniQuadraticPen or HoudniCubicPen, which takes a series of input
    path moves and control points and writes to houdini's geometry. The performance impact of
    HoudiniPen should be pretty similar across both methods since they're kinda doing the same thing (
    Iterating through and calling the relevant move).

    Method 1 (Currently in use and required by the pathops simplify setup):
        fontgoggle.shaper.font.draw_glyph_with_pen(glyph.gid, HoudiniPen )

    Method 2 (NOT in use):
        outline = fontgoggle._getGlyphOutline(glyph_name)
        for mv, pts in outline.value:
            getattr(HoudiniPen, mv)(*pts)

    Speed order on super long_test_text (2 paragraphs of lorem ipsum):
    1) ~0.085 - Debug ON   Method 1
    2) ~0.170 - Debug ON   Method 2
    3) ~0.370 - Debug OFF  Method 2
    4) ~0.840 - Debug OFF  Method 1

    These results are shockingly consistent, but incomprehensible.
    I literally cannot explain this in the slightest.
    """
    # profiler = cProfile.Profile(subcalls=False, builtins=False)
    # profiler.enable(subcalls=False, builtins=False)
    
    textparm = interfacenode.parm('text')
    src_text = textparm.eval() if textparm else ''
    font_info = eval( node.evalParm("font_info") )

    try:
        typecasterfont = tcf.Font.Cacheable( font_info[0], number=font_info[1] )
    except tcf.FontNotFoundException as e:
        msg = f"""Font "{font_info[0]}" does not exist or failed to initialize!"""
        msg += " FontNotFoundException" + (f": {str(e)}" if str(e) else "")
        raise hou.NodeError(msg)

    fontgoggle = typecasterfont.font
    # ttfont:ttLib.TTFont = fontgoggle.ttFont
    # glyphSet = fontgoggle.ttFont.getGlyphSet()

    # HOUDINI ATTRIBUTE SETUP
    # This attribute contains the array of positional information needed to draw each individual glyph.
    attrib_ctrlpts = geo.addArrayAttrib(hou.attribType.Point, "ctrlpts", hou.attribData.Float)

    # These are used by both the glyphs and the skeleton
    attrib_ids = geo.addArrayAttrib(hou.attribType.Point, "ids", hou.attribData.Int)
    attrib_prim_ids = geo.addArrayAttrib(hou.attribType.Prim, "ids", hou.attribData.Int)

    # These are only used by the skeleton
    attrib_skeltype = geo.addAttrib(hou.attribType.Point, "skeltype", "", create_local_variable=False)
    attrib_gsz = geo.addArrayAttrib(hou.attribType.Point, "gsz", hou.attribData.Float)
    attrib_gshift = geo.addAttrib(hou.attribType.Point, "gshift", (0.,0.), create_local_variable=False)
    grp_skel = geo.createPointGroup('skeleton')

    # Try and get the vertical height of the given glyph, and if there isn't one assume that
    # we're working with a standard Latin font and get the sCapHeight from the OS/2 table
    vmtx = fontgoggle.ttFont.get('vmtx')
    os2 = fontgoggle.ttFont.get('OS/2')
    if os2 is None:
        raise NotImplementedError("It looks like some fonts don't always use OS/2. Is there a fallback besides a default value?")
    sCapHeight = os2.sCapHeight if hasattr(os2, "sCapHeight") else 0
    if sCapHeight == 0: sCapHeight = os2.sTypoAscender if hasattr(os2, "sTypoAscender") else 750

    # Set the overall scale of each glyph to be applied in Houdini, to ensure general sizing is consistent between fonts.
    upem = fontgoggle.unitsPerEm
    glyphscale = 1000/upem
    attrib_glyphscale = geo.addAttrib(hou.attribType.Global, "_glyphscale", 1., create_local_variable=False)
    geo.setGlobalAttribValue(attrib_glyphscale, glyphscale)

    linespace = typecasterfont.best_line_spacing
    attrib_linespacing = geo.addAttrib(hou.attribType.Global, "_lineSpacing", 1., create_local_variable=False)
    geo.setGlobalAttribValue(attrib_linespacing, (linespace*glyphscale)/1000)

    # Find all the feature folders and get the value of the parameters within
    ptg = interfacenode.parmTemplateGroup()
    featfolder_name = "general_features"; ssfolder_name = "stylistic_sets"; cvfolder_name = "character_variants"

    # folder = ptg.find(featfolder_name)
    # features = { parm.name() : interfacenode.parm(parm.name()).eval() == 1 for parm in folder.parmTemplates() }
    # folder = ptg.find(ssfolder_name)
    # features.update({ parm.name() : interfacenode.parm(parm.name()).eval() == 1 for parm in folder.parmTemplates() })
    # folder = ptg.find(cvfolder_name)
    # features.update({ parm.name() : interfacenode.parm(parm.name()).eval() == 1 for parm in folder.parmTemplates() })
    """
    FIXME:
    Ok for reasons that are beyond my comprehension the second the top-level parameter folders are set to tabs,
    it becomes essentially impossible to access the folders normally. While they might appear normal in the type
    properties pane, looking at the parameter interface of an actual placed node reveals that a number gets
    appended to the name of almost every single folder.

    It appears to correspond to the number of elements in the folder set +1. So for example:
    type_config      ---> type_config4 (It has 3 elements in it's set of tabs)
    general_features ---> general_features2 (It's a simple folder so it only has one folder)

    This behavior doesn't happen in a non-HDA version of the interface, so it must be some quirk exclusive to HDAs.
    It's worth noting that this also happens on native SideFX nodes like the Sop FLIP solver node.

    EVEN MORE annoyingly, this doesn't seem to be the case when the node is in it's default state, or at least
    it is still possible to access the folders using their intended names, so it's necessesary to add an extra
    condition for every single folder accessed to first try it's intended name and then a version with the number appended.

    This honestly isn't too expensive to account for, but it inhenrently requires this script to remain directly coupled to
    the asset since the number being appended is completely dependent on the interface it is accessing. While it's likley
    possible to do this programatically by getting then length of the set of folder names with the FolderSetParmTemplate,
    I don't want to give in to this issue by affording it any more computation than is absolutely needed.
    """
    targetfolder = ptg.find(featfolder_name)
    if not targetfolder: targetfolder = ptg.find(featfolder_name+'2')
    features = { parm.name() : interfacenode.parm(parm.name()).eval() == 1 for parm in targetfolder.parmTemplates() }

    targetfolder = ptg.find(ssfolder_name)
    if not targetfolder: targetfolder = ptg.find(ssfolder_name+'2')
    features.update({ parm.name() : interfacenode.parm(parm.name()).eval() == 1 for parm in targetfolder.parmTemplates() })

    targetfolder = ptg.find(cvfolder_name)
    if not targetfolder: targetfolder = ptg.find(cvfolder_name+'2')
    features.update({ parm.name() : interfacenode.parm(parm.name()).eval() == 1 for parm in targetfolder.parmTemplates() })

    # Kerning causes some complexities with my optimizations for per-glyph variation, so we can take some shortcuts if it's disabled.
    featuresGPOS = fontgoggle.featuresGPOS
    font_using_kern = True if 'kern' in featuresGPOS and features.get('kern', True) else False

    # Read in the parameter setting for preprocessing glyphs for when variation axes should cause glyph swaps.
    # TODO: I think it's possible to identify if the opentype table for varaxes GSUBs is present and only
    # use this setting if it's needed. Not sure though. Since this operation is super expensive I'd like to
    # prevent it from running whenever possible.
    tparm:hou.Parm = interfacenode.parm('reprocess_varying_for_glyphsub')
    reprocess_for_glyphswap = tparm.eval() if tparm else False
    del tparm

    # Below is for handling an extreme edgecase where incoming varaxes use parameter-incompatible naming.
    # I'm not sure if there's any meaningful overhead from grabbing another node's python module,
    # but this is the most robust way I can think of to ensure the naming scheme used is identical to
    # when the parameters are created.
    ensure_compatible_name = interfacenode.hdaModule().ensure_compatible_name

    # If the necessary inputs are used, configure for per-glyph variation
    variations = {}
    attrib_varying_per_glyph = geo.addAttrib(hou.attribType.Global, "__varying_per_glyph", False, create_local_variable=False)
    varying_per_glyph = False
    font_is_varying= fontgoggle.shaper.face.has_var_data
    if font_is_varying:
        variation_axes = fontgoggle.axes
        attribstatus = {}
        nodeinputs = node.inputs()
        try:
            geoin1: hou.Geometry = nodeinputs[1].geometry()
            if geoin1.attribValue('__input_has_axes') == True:
                hpoints = geoin1.points()
                varying_per_glyph = True
                geo.setGlobalAttribValue(attrib_varying_per_glyph, True)
                attribstatus = { attrib.name() : [attrib,] for attrib in geoin1.pointAttribs() }
        except IndexError:
            hpoints = []

        geoin2:hou.Geometry = nodeinputs[2].geometry()
        for var in variation_axes:
            # varcompat = ensure_compatible_name(var+'_real')
            # # Above handles an extreme edgecase where incoming varaxes use parameter-incompatible naming.
            # parm = interfacenode.parm(varcompat)
            # if parm is not None:
            #     variations[var] = parm.eval()
            try:
                variations[var] = geoin2.attribValue(ensure_compatible_name(var))
            except hou.OperationFailed:
                pass
    else:
        hpoints = []
    
    bezier_order = typecasterfont.bezier_order
    attrib_bezier_order = geo.addAttrib(hou.attribType.Global, "__bezier_order", 3, create_local_variable=False)
    geo.setGlobalAttribValue(attrib_bezier_order, bezier_order)
    if bezier_order == 3:
        HoudiniPen = HoudiniQuadraticPen( geo=geo, attrib_ctrlpts=attrib_ctrlpts)
    elif bezier_order == 4:
        HoudiniPen = HoudiniCubicPen( geo=geo, attrib_ctrlpts=attrib_ctrlpts)

    # HoudiniPen.closefunc = increment_point_attribs

    def newline(line_idx):
        """Create a point and polygon for the next line with the relevant attributes"""
        linept = geo.createPoint()
        linept.setAttribValue( attrib_skeltype, "line" )
        linept.setAttribValue( attrib_ids, [ line_idx, ] )
        # linept = createPoint_delayedAttribs(skeltype='line', ids=[ line_idx, ])
        grp_skel.add(linept)
        blockpoly.addVertex(linept)
        linepoly = geo.createPolygon(is_closed=False)
        linepoly.addVertex(linept)
        return linepoly
    
    def new_glyphpt_skel( linepoly, gsz, ids, offset=None):
        glyphpt_skel = geo.createPoint()
        glyphpt_skel.setAttribValue( attrib_skeltype, "glyph" )
        glyphpt_skel.setAttribValue( attrib_gsz, gsz )
        glyphpt_skel.setAttribValue( attrib_ids, ids )
        if offset is not None:
            glyphpt_skel.setAttribValue( attrib_gshift, offset )
        # glyphpt_skel = createPoint_delayedAttribs(skeltype='glyph', gsz=gsz, ids=ids)
        grp_skel.add(glyphpt_skel)
        linepoly.addVertex(glyphpt_skel)
        return glyphpt_skel

    def new_glyphpt_skel_extension( gsz, ids, offset, target_glyphpt_skel):
        glyphpt_skel_extension = geo.createPoint()
        glyphpt_skel_extension.setAttribValue( attrib_skeltype, "glyphextension" )
        glyphpt_skel_extension.setAttribValue( attrib_gsz, gsz )
        glyphpt_skel_extension.setAttribValue( attrib_ids, ids )
        glyphpt_skel_extension.setAttribValue( attrib_gshift, offset )
        # glyphpt_skel_extension = createPoint_delayedAttribs(skeltype='glyphextension', gsz=gsz, ids=ids, gshift=offset)
        grp_skel.add(glyphpt_skel_extension)
        extensionpoly = geo.createPolygon(is_closed=False)
        extensionpoly.addVertex(target_glyphpt_skel)
        extensionpoly.addVertex(glyphpt_skel_extension)

    # Create the main point for the text block
    blockpt = geo.createPoint()
    blockpt.setAttribValue( attrib_skeltype, "block" )
    # blockpt = createPoint_delayedAttribs(skeltype='block')
    grp_skel.add(blockpt)
    blockpoly = geo.createPolygon(is_closed=False)
    blockpoly.addVertex(blockpt)

    stable_idx = 0
    true_idx = 0
    linestart = 0
    run_id_current = 0
    unique_glyphs = {}

    bidiparm:hou.Parm = interfacenode.parm('use_bidi_segmentation')
    use_bidi_segmentation = bidiparm.eval() if bidiparm else False
    del bidiparm

    # Iterate through each line in the input string independently, to avoid any issues passing newlines to harfbuzz
    for line_id, line_text in enumerate(src_text.split("\n")):

        # Create the poly for the line about to be operated on
        linepoly = newline(line_id)

        # Process the input string
        """
        Using the complex_string system can have a meaningful impact on larger strings, so it's probably best to leave
        selecting this up to the user.

        The main usecase for this is when RTL and LTR scripts are being used in the same line, often seen in Arabic
        since it is generally written right to left while numbers are stil left to right. While this likely can be useful
        in other cases, handling an Arabic line with a number in it was the motivation for this functionality.
        """
        glyph_runs = []
        if use_bidi_segmentation:
            run_info = []
            reordered_segments, run_id_current, run_info = line_to_run_segments(line_text, run_id_current, run_info)
            for segment in reordered_segments:
                glyph_runs.append( (fontgoggle.shaper.shape( segment[0], features=features, varLocation=variations, direction=segment[1]), segment[0], segment[3]) )
        else:
            if line_text != "":
                glyph_runs.append( (fontgoggle.shaper.shape( line_text, features=features, varLocation=variations), line_text, 0) )

        glyphqueue = []
        for current_runidx, (glyph_run, run_text, run_start) in enumerate(glyph_runs):
            # Detect if the current chunk is reversed
            # This seems like a pretty quick-and-dirty way to do it, but it works so far (famous last words)
            is_reversed  = False
            if glyph_run[-1].cluster < glyph_run[0].cluster:
                is_reversed = True

            # The is the start index of the current text run, accounting for previous line's runs
            run_start_full = linestart+run_start

            glyph_cluster_last = -1
            line_idx = 0
            for glyph_idx, glyph in enumerate(glyph_run):
                glyph_name = glyph.name
                glyph_cluster_next = -1
                glyph_cluster = glyph.cluster
                if is_reversed:
                    if glyph_idx > 0:
                        try:
                            glyph_cluster_next = glyph_run[ glyph_idx+1 ].cluster
                        except IndexError:
                            pass
                        # glyph_cluster_prev = glyph_run[ glyph_idx-1 ].cluster
                        # clustersize = glyph_cluster_prev - glyph_cluster
                        clustersize = glyph_cluster - glyph_cluster_next
                    else:
                        glyph_cluster_next = glyph_run[ glyph_idx+1 ].cluster
                        clustersize = len(run_text) - glyph_cluster
                else:
                    try:
                        glyph_cluster_next = glyph_run[ glyph_idx+1 ].cluster
                        clustersize = glyph_cluster_next-glyph_cluster
                    except IndexError:
                        clustersize = len(run_text) - glyph_cluster

                # The is the main section to get all the needed information associated with the current glyph and operate on it.
                glyph_already_exists = False
                ax_nokern = None
                glyph_variations = variations
                if varying_per_glyph:
                    # Set the per-glyph variations
                    glyph_variations = variations.copy()
                    try:
                        for var in variation_axes:
                            varcompat = ensure_compatible_name(var)
                            if varcompat in attribstatus:
                                glyph_variations[var] = hpoints[stable_idx].attribValue(varcompat)
                    except IndexError:
                        pass
                    
                    needs_run = True
                    # Below is an extremely experimental system to reprocess a given tex run for glyph variations. This doesn't catch if the number of glyphs changes though.
                    if reprocess_for_glyphswap:
                        try:
                            glyph = fontgoggle.shaper.shape( run_text, features=features, varLocation=glyph_variations, direction=None, language=None, script=None)[glyph_cluster]
                            ax = glyph.ax
                            needs_run = False
                        except IndexError:
                            pass
                    
                    if font_using_kern and needs_run:
                        """
                        Processing each glyph independently inherentently removes any kerning pair positioning.
                        To recover this information, a minimally-sized string is passed to the shaper. The performance hit of running the entire string
                        through the shaper again isn't worth it, but grabbing fragments has a much higher chance of erroring with languages like Arabic.
                        The main downside of this is that it likely won't catch kern configs that occur with more than 2 successive characters,
                        although these are pretty rare in fonts (though they are supported in the OpenType spec, so maybe I should account for them...).
                        
                        TODO: This is a fairly expensive operation and could likely be optimized if there were some way to directly pass the current glyph's
                        name and the next glyph's name.
                        Additionally, if it were possible to obtain a list of existing kern pairs in the font this could also be used to accelerate everything.
                        """
                        minimal_text_approx = run_text[glyph_cluster:glyph_cluster+clustersize+1]
                        reglyph = fontgoggle.shaper.shape( minimal_text_approx, features=features, varLocation=glyph_variations, direction=None, language=None, script=None)[0]
                        # reglyph = fontgoggle.shaper.shape( run_text, features=features, varLocation=glyph_variations, direction=None, language=None, script=None)[glyph_idx]

                        # Check if the glyph created from the subset of the current line actually is the same as what harfbuzz did for the full line. This should avoid incorrect glyphs being used for complex clusters.
                        if reglyph.name == glyph.name:
                        # if True and not is_reversed:
                            ax = reglyph.ax
                            glyph = reglyph
                        else:
                            # fallback to glyph's default advance without kerning
                            ax = fontgoggle.shaper.font.get_glyph_h_advance(glyph.gid)
                    else:
                        # Update advance size given the current variable font axes
                        fontgoggle.shaper.font.set_variations(glyph_variations)
                        ax = fontgoggle.shaper.font.get_glyph_h_advance(glyph.gid)
                else:
                    # ax = fontgoggle.shaper.font.get_glyph_h_advance(glyph.gid)
                    ax = glyph.ax
                    if font_using_kern:
                        ax_nokern = fontgoggle.shaper.font.get_glyph_h_advance(glyph.gid)

                # Set all of the different ids for each glyph.
                # This is essentially every possible identifier that might be used to segment or identify a given input string.
                """
                Glossary of provided IDs:
                
                line_id
                    The number of the current line in the source text
                stable_idx
                    This is a left-to-right index of the current text block, with it's number incremented for each shaped glyph
                    output left to right. This numbering stays consistent irrespective of RTL or LTR type, which can be helpful
                    for Houdini-centric modifications or things like sin functions.
                true_idx
                    This number is incremented for each glyph output by the shaper, in addition to any new lines. Unlike stable_idx,
                    which takes into account the cluster size, this value always increments by 1 for each glyph iterated over
                glyph.gid
                    This is the id of the current glyph within the font. This should output unique ids for each glyph used from the font,
                    so it can be useful for things like instancing or applying things to all occurances of a given glyph. Please note
                    that this number is NOT stable across fonts.
                source_idx
                    This is intended to map to the source character in the input string used in the creation of a given glyph.
                    This should most often end up being the "reading order" for the output type.
                codepoint_lazy
                    This is only really intended to be used as a drop-in replacement for the inbuilt Font node's textsymbol attribute.
                    This value does NOT take into account complex shaping features or ligatures, and simply gets the unicode codepoint
                    for the first character in a cluster.
                line_idx
                    The index of the glyph within the current line. This is essentially stable_idx, but resetting for each line
                glyph_hash
                    Unique hash of the glyph's ID and varying information.
                run_id
                    The ID for the current text run. In a standard LTR multiline string, this will be the same as line_id, but in the case of
                    bidirectional text, it will be based off of individual runs, taking into account line directions
                """
                codepoint_lazy = ord(run_text[glyph_cluster])
                source_idx = run_start_full+glyph_cluster
                dictstring = f"glyph{glyph.gid}"+str(sorted(glyph_variations.items()))
                glyph_hash = hash(dictstring)
                run_id = run_info[current_runidx][0] if use_bidi_segmentation else line_id
                ids = [ line_id, stable_idx, true_idx, glyph.gid, source_idx, codepoint_lazy, line_idx, glyph_hash, run_id]

                # Check if the glyph has already been created, and mark it as existing if so.
                if glyph_hash in unique_glyphs:
                    unique_glyphs[glyph_hash] += 1
                    glyph_already_exists = True
                else:
                    unique_glyphs[glyph_hash] = 1

                # If there is a vertical metrics table, use that for the y size, rather than the sCapHeight.
                # this is mainly found in CJK and similar language fonts.

                if vmtx:
                    gsz = [float(ax), float(vmtx.metrics.get(glyph_name,0)[0])]
                    if gsz[1] == 0:
                        gsz[1] = float(sCapHeight)
                else:
                    gsz = [float(ax), float(sCapHeight)]

                # This condition is now caught in the vmtx condition above by falling back to the sCapHeight value. This might cause issues with vertical scripts.
                # if gsz[1] == 0:
                #     print(f"---------- NOT SUPPOSED TO HAPPEN: The current glyph's height is 0 ({glyph_name} with ({gsz}))--------------")

                # For use with pivot adjustment, this appends a "standard" version of the glyph's size (width) that doesn't use kern pairs.
                if font_using_kern and ax_nokern is not None:
                    gsz.extend( [ ax_nokern, gsz[1] ] )

                run_standard_glyph = True
                offset = (float(glyph.dx),float(glyph.dy))
                if is_reversed:
                    if glyph_cluster == glyph_cluster_next:
                        # If the current glyph_cluster is the same as the next, assume that it's (for example) an additional element like dots above and below in Arabic
                        run_standard_glyph = False
                        # It's likely possible to slightly optimize things by explicitly declaring things like direction and language, since they should be known
                        reglyph = fontgoggle.shaper.shape(run_text, features=features, varLocation=glyph_variations, direction=None, language=None, script=None)[glyph_idx]
                        glyphqueue.append( ( gsz, ids, offset) )
                else:
                    if glyph_cluster == glyph_cluster_last:
                        """
                        For a majority of standard latin-based fonts, this will likely never get activated.

                        That said, a pretty complex case that causes this to trigger is the cursive font family Playwrite.
                        Using glyphqueue generally works pretty well but in some cases I feel like the secondary marks
                        bind to the incorrect main glyph. That said this isn't consistent so it's likely a quirk of Playwrite
                        """
                        run_standard_glyph = False
                        # msg = f"Unusual case for zero-length cluster staging. If you see this message and aren't the author, if possible please submit the font you were using which caused this so I can expand the functionality."
                        # msg += f"\n(gname:{glyph_name}, gid:{ids[3]}, run_txt:{run_text}, glyph_idx:{glyph_idx})"
                        # raise NotImplementedError(msg)
                        # print(msg)
                        # new_glyphpt_skel( linepoly, gsz, ids)
                        # new_glyphpt_skel_extension( gsz=gsz, ids=ids, offset=offset, target_glyphpt_skel=glyphpt_skel)
                        glyphqueue.append( ( gsz, ids, offset) )

                if run_standard_glyph:
                    if offset[0] != 0.0 or offset[1] != 0.0:
                        glyphpt_skel = new_glyphpt_skel( linepoly, gsz, ids, offset)
                    else:
                        glyphpt_skel = new_glyphpt_skel( linepoly, gsz, ids)
            
                    if glyphqueue:
                        # The glyphqueue is used to place markings AFTER their main glyph even when the markings show up first in the glyph
                        # run. This doesn't have any effect on the various idx values since they are conserved, but it allows for a
                        # more correct rig heirarchy.
                        for (lastdata) in glyphqueue:
                            new_glyphpt_skel_extension( gsz=lastdata[0], ids=lastdata[1], offset=lastdata[2], target_glyphpt_skel=glyphpt_skel)
                        glyphqueue = []

                if not glyph_already_exists:
                    # Create the polygon for the current glyph, which will contain the construction points needed for the individual bezier paths
                    glyphpoly = geo.createPolygon(is_closed=True)
                    glyphpoly.setAttribValue( attrib_prim_ids, ids )

                    HoudiniPen.polygon = glyphpoly

                    remove_overlaps = interfacenode.evalParm('remove_glyph_overlaps')
                    if remove_overlaps:
                        p1 = PathopsPath()
                        
                        # gset = glyphSet[glyph.name]
                        # gset.draw(p1.getPen(glyphSet=glyphSet))
                        fontgoggle.shaper.font.draw_glyph_with_pen(glyph.gid, p1.getPen())

                        p1.simplify(fix_winding=True, keep_starting_points=True, clockwise=True)
                        HoudiniPen.output_from_pathops_path(p1)                
                    else:

                        # outline = fontgoggle._getGlyphOutline(glyph_name)
                        # for mv, pts in outline.value:
                            # getattr(HoudiniPen, mv)(*pts)
                        
                        fontgoggle.shaper.font.draw_glyph_with_pen(glyph.gid, HoudiniPen )
                        
                        # The following fixes the winding direction, but roughly doubles the cost of outputting,
                        # since it has to create each path as a pathops pen, and then a Houdini pen
                        # this is also a large factor in why remove_overlaps costs more, in addition to the additional
                        # calculations
                        # also, this doesn't really catch everything since it operates over the entire glyph and not subcomponents
                        # So for an exclamation point the dot could have the correct winding dirrection but the line could be wrong

                        # p1 = PathopsPath()
                        # fontgoggle.shaper.font.draw_glyph_with_pen(glyph.gid, p1.getPen() )
                        # if not p1.clockwise:
                        #     p1.reverse()
                        # HoudiniPen.output_from_pathops_path(p1) 

                # Increment stable_idx by the size of the current_glyph's cluster, in addition to the line index, which resets for each line
                stable_idx += clustersize
                line_idx += clustersize
                # Increment true_idx by 1 nomatter what
                true_idx += 1

                glyph_cluster_last = glyph_cluster

        # Add the current line length
        linestart += len(line_text)+1

        # For each new line, increment stable_idx by 1
        stable_idx += 1
    
    # profiler.disable()
    # import pstats
    # pstats.Stats(profiler).sort_stats('ncalls').print_stats()