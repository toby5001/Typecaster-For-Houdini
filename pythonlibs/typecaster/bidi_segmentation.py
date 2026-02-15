"""

Submodule for bidirectional segmentation. This is a fairly simple wrapper for the 
python-bidi module, creating usable segments for Typecaster's core with the apropriate 
accompanying metadata.

"""

from __future__ import annotations
from bidi.algorithm import (  # noqa: ignore E402
    get_empty_storage, get_base_level, get_embedding_levels,
    explicit_embed_and_overrides, resolve_weak_types,
    resolve_neutral_types, resolve_implicit_levels,
    reorder_resolved_levels,
)


def line_to_run_segments(line_text, run_id_current=0, run_info=[]):
    """Break a line of potentially bidirectional text into Typecaster-compatible text runs for use with uharfbuzz.

    Args:
        line_text (str): A single line of text to segment.
        run_id_current (int, optional): The current run_id, set across multiple runs of the function. Defaults to 0.
        run_ids (list, optional): Continuous list of run_ids, set across multiple runs of the function. Defaults to [].

    Returns:
        list[str,int,list[int]]: Returns a tuple of the line segment info, new run_id_current, and modified run_ids.
    """    
    debug=False
    storage = get_empty_storage()
    upper_is_rtl = False
    base_level = get_base_level(line_text, upper_is_rtl)
    storage['base_level'] = base_level
    storage['base_dir'] = ('L', 'R')[base_level]

    """
    Broadly follows the Unicode Bidirectional Algorithm order (through python-bidi),
    but without any of the paragraph-level operations (since this operation is run per-line)
    For more info: https://unicode.org/reports/tr9/#Resolving_Embedding_Levels
    """
    get_embedding_levels(line_text, storage, upper_is_rtl, debug)

    explicit_embed_and_overrides(storage, debug)
    resolve_weak_types(storage, debug)
    resolve_neutral_types(storage, debug)
    resolve_implicit_levels(storage, debug)
    reorder_resolved_levels(storage, debug)
    # I'm not sure why, but using apply_mirroring doesn't seem to work as it should, and the output without is fine.
    # Perhaps harfbuzz is handling that step since it's technically part of shaping?
    # apply_mirroring(storage, debug)
    
    # new_segments  = []
    # prev_type = None
    # for char in storage['chars']:
    #     if char['type'] == prev_type:
    #         seg += char['ch']
    #         typ = char['type']
    #     elif prev_type is None:
    #         seg = char['ch']
    #     else:
    #         new_segments.append( (seg, typ) )
    #         seg = char['ch']
    #     prev_type = char['type']
    # if seg:
    #     new_segments.append( (seg, typ) )

    isRTL = base_level % 2
    reordered_segments = []
    run_lengths = []
    index = 0
    
    # segmentation = itertools.groupby( storage['chars'], key=lambda item: item['level'] % 2)
    # This should be functionally identical to the above groupby, but with clearer behavior and less problems with nested group objects.
    segmentation = []
    sidx = -1
    llevel = -1
    for char in storage['chars']:
        # In comparison to fontgoggles, I'm segmenting based off of a difference in character level,
        # and NOT a change in detected script.
        clevel = char['level'] % 2
        if llevel != clevel:
            sidx += 1
            segmentation.append( (clevel, [char,]) )
        else:
            segmentation[sidx][1].append(char)
        llevel = clevel                    
    
    # Reverse the input segment order if the current input's base_level is RTL
    if isRTL:
        segmentation.reverse()

    for value, sub in segmentation:
        run_info.append( (run_id_current, value%2, isRTL) )
        run_id_current += 1
        # This method is not the same as what fontgoggles does, but I've diverged pretty significantly at this point so maybe that's alright
        if value%2:
            # print("<HIT> Reverse R subsegment")
            sub = reversed(sub)
            dir = "R"
        else:
            # print("<HIT> Straight L subsegment")
            dir = "L"
        
        runChars = u''
        counter = 0
        for chardat in sub:
            runChars += chardat['ch']
            counter += 1
        run_lengths.append(counter)
        next_index = index + counter
        reordered_segments.append( (runChars, dir, value, index) )
        index = next_index
    
    # Undo the reversal (if needed)
    if isRTL:
        reordered_segments.reverse()
        run_info.reverse()
    
    return reordered_segments, run_id_current, run_info