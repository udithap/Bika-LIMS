""" Reference Definitions represent standard specifications for
    reference samples used in quality control
"""
from AccessControl import ClassSecurityInfo
from DateTime import DateTime
from Products.Archetypes.public import *
from Products.CMFCore.permissions import View, ModifyPortalContent
from bika.lims.content.bikaschema import BikaSchema
from bika.lims.browser.fields import ReferenceResultsField
from bika.lims.browser.widgets import ReferenceResultsWidget
from bika.lims.config import PROJECTNAME
import sys
import time
from bika.lims import PMF, bikaMessageFactory as _
from zope.interface import implements

schema = BikaSchema.copy() + Schema((
    ReferenceResultsField('ReferenceResults',
        schemata = PMF('Reference Results'),
        required = 1,
        widget = ReferenceResultsWidget(
            label = _("Reference Results"),
            description = _("Click on Analysis Categories (against shaded background) "
                            "to see Analysis Services in each category. Enter minimum "
                            "and maximum values to indicate a valid results range. "
                            "Any result outside this range will raise an alert. "
                            "The % Error field allows for an % uncertainty to be "
                            "considered when evaluating results against minimum and "
                            "maximum values. A result out of range but still in range "
                            "if the % error is taken into consideration, will raise a "
                            "less severe alert."),
        ),
    ),
    BooleanField('Blank',
        schemata = PMF('Description'),
        default = False,
        widget = BooleanWidget(
            label = _("Blank"),
            description = _("Reference sample values are zero or 'blank'"),
        ),
    ),
    BooleanField('Hazardous',
        schemata = PMF('Description'),
        default = False,
        widget = BooleanWidget(
            label = _("Hazardous"),
            description = _("Samples of this type should be treated as hazardous"),
        ),
    ),
))

schema['title'].schemata = PMF('Description')
schema['title'].widget.visible = True
schema['description'].schemata = PMF('Description')
schema['description'].widget.visible = True

class ReferenceDefinition(BaseContent):
    security = ClassSecurityInfo()
    displayContentsTab = False
    schema = schema

    _at_rename_after_creation = True
    def _renameAfterCreation(self, check_auto_id=False):
        from bika.lims.idserver import renameAfterCreation
        renameAfterCreation(self)

registerType(ReferenceDefinition, PROJECTNAME)
