"""

Submodule for a pen class similar in style and functionality to many common fontTools pens.
This is intended for use with the outlines of a font's glyphs.

"""


import hou
try:
    from pathops import PathVerb
except ImportError:
    PathVerb = None
    pass


__CTRLPTS_ATTRIBNAME__ = "ctrlpts"

class HoudiniBasePen():
    """
    This is the base class for outputting control points directly to Houdini.
    This class should not be directly instantiated, and instead either HoudiniCubicPen or HoudiniQuadraticPen should be used.
    """
    bezier_order = None
    def __init__(self, geo:hou.Geometry, attrib_ctrlpts:hou.Attrib=None, polygon:hou.Polygon=None):
        """
        Initialize a Houdini Pen.

        Args:
            bezier_order(int):
                The order of the current bezier being created.
            geo (hou.Geometry):
                Geometry object to write the control point information to.
            attrib_ctrlpts (hou.Attrib):
                Attribute which should be used for writing the control point information. If not specified,
                an attribute will be created.
            polygon (hou.Polygon):
                The polygon which the new point will be connected to. This is often specified after
                the initial creation of the Pen object. Ignored if not specified. 

        """
        if type(self) is HoudiniBasePen:
            raise Exception("<HoudiniBasePen> must be subclassed.")
        
        self.ptsset = []
        self.geo = geo
        self.polygon = polygon

        if not attrib_ctrlpts:
            self.attrib_ctrlpts:hou.Attrib = geo.findPointAttrib(__CTRLPTS_ATTRIBNAME__)
            if self.attrib_ctrlpts is not None:
                self.attrib_ctrlpts:hou.Attrib = geo.addArrayAttrib(hou.attribType.Point, __CTRLPTS_ATTRIBNAME__, hou.attribData.Float)
        else:
            self.attrib_ctrlpts = attrib_ctrlpts

    def closePath(self):
        "Create a new point in Houdini for the current array of control points, and then clear the list."
        pt = self.geo.createPoint()
        if self.polygon:
            self.polygon.addVertex(pt)
        pt.setAttribValue( self.attrib_ctrlpts, self.ptsset)
        self.ptsset = []

    def endPath(self):
        raise NotImplementedError("Unsupported move of endPath called. This should not happen is regular usage.")
    
    def qCurveTo(self, *args):
        raise NotImplementedError("Unsupported move of qCurveTo called. Are you using the right curve type?")
    
    def curveTo(self, *args):
        raise NotImplementedError("Unsupported move of curveTo called. Are you using the right curve type?")
    
    def output_from_pathops_path(self, path):
        """
        Call the needed operations to write a pathops path, iterating though each move and set of points.
        """
        if PathVerb is not None:
            for mv, pts in path:
                if mv == PathVerb.MOVE:
                    self.moveTo(*pts)
                elif mv == PathVerb.CUBIC:
                    self.curveTo(*pts)
                elif mv == PathVerb.QUAD:
                    self.qCurveTo(*pts)
                elif mv == PathVerb.LINE:
                    self.lineTo(*pts)
                elif mv == PathVerb.CLOSE:
                    self.closePath()
        else:
            raise NotImplementedError("Pathops is not installed, or could not be initialized!")


class HoudiniQuadraticPen(HoudiniBasePen):
    """
    Pen for constructing a Quadratic bezier curve in Houdini.

    Creates a new point in the given geostream with an array of point coordinates.
    """
    bezier_order = 3

    def moveTo(self, pt1):
        self.ptsset.extend( [ pt1[0], pt1[1], pt1[0], pt1[1] ] )

    def lineTo(self, pt1):
        self.ptsset.extend( [ pt1[0], pt1[1], pt1[0], pt1[1] ] )

    def qCurveTo(self, pt1, pt2):
        self.ptsset.extend( [ pt1[0], pt1[1], pt2[0], pt2[1] ] )
    # Unless it's really required I don't think it's a good idea to support curveTo here, since lowering
    # the order of a curve is lossy. Maybe worth looking to as an advanced toggle? (If it's ever an issue)


class HoudiniCubicPen(HoudiniBasePen):
    """
    Pen for constructing a Cubic bezier curve in Houdini.

    Creates a new point in the given geostream with an array of point coordinates.

    Includes support for quadratic curveTo moves, although the implementation hasn't been confirmed to be
    mathematically correct.
    """
    bezier_order = 4

    def moveTo(self, pt1):
        self.ptsset.extend( [ pt1[0], pt1[1], pt1[0], pt1[1], pt1[0], pt1[1] ] )

    def lineTo(self, pt1):
        self.ptsset.extend( [ pt1[0], pt1[1], pt1[0], pt1[1], pt1[0], pt1[1] ] )

    def curveTo(self, pt1, pt2, pt3):
        self.ptsset.extend( [ pt1[0], pt1[1], pt2[0], pt2[1], pt3[0], pt3[1] ] )

    def qCurveTo(self, pt1, pt2):
        # I think this has an extremely rare chance of happening with the pathops simplify operation?
        self.ptsset.extend( [ pt1[0], pt1[1], pt2[0], pt2[1], pt2[0], pt2[1] ] )
        # Visually, this seems to be good enough, but I don't think it's mathematically the same as correctly 
        # converting from quadratic to cubic.


def getHoudiniPen( bezier_order:int, *args, **kwargs):
    """
    Factory function for creating an appropriate HoudiniPen based off of the bezier order

    Args:
        bezier_order(int):
            The order of the current bezier being created.
        geo (hou.Geometry):
            Geometry object to write the control point information to.
        attrib_ctrlpts (hou.Attrib):
            Attribute which should be used for writing the control point information. If not specified,
            an attribute will be created.
        polygon (hou.Polygon):
            The polygon which the new point will be connected to. This is often specified after
            the initial creation of the Pen object. Ignored if not specified. 
    """
    if bezier_order == 3:
        return HoudiniQuadraticPen( *args, **kwargs)
    elif bezier_order == 4:
        return HoudiniCubicPen( *args, **kwargs)
    else:
        raise NotImplementedError(f"Unsupported Bezier Order! ({bezier_order})")