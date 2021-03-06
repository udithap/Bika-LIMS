from AccessControl import ClassSecurityInfo
from Products.Archetypes.public import *
from Products.Archetypes.references import HoldingReference
from Products.CMFCore.utils import getToolByName
from bika.lims import bikaMessageFactory as _
from bika.lims.config import PROJECTNAME
from bika.lims.content.bikaschema import BikaSchema
import sys

schema = BikaSchema.copy() + Schema((
    BooleanField('PrePreserved',
        default = False,
        widget = BooleanWidget(
            label = _("Pre-preserved"),
            description = _("Check this box if this container is already preserved."
                            "Setting this will short-circuit the preservation workflow "
                            "for sample partitions stored in this container."),
        ),
    ),
    ReferenceField('Preservation',
        required = 0,
        vocabulary_display_path_bound = sys.maxint,
        allowed_types = ('Preservation',),
        vocabulary = 'getPreservations',
        relationship = 'ContainerPreservation',
        referenceClass = HoldingReference,
        widget = ReferenceWidget(
            checkbox_bound = 1,
            label = _("Preservation"),
            description = _("If this container is pre-preserved, then the preservation "
                            "method could be selected here."),
        ),
    ),
    StringField('Capacity',
        required = 0,
        default = "0 ml",
        widget = StringWidget(
            label = _("Capacity"),
            description = _("Maximum possible size or volume of samples."),
        ),
    ),
    ReferenceField('ContainerType',
        required = 0,
        vocabulary_display_path_bound = sys.maxint,
        allowed_types = ('ContainerType',),
        vocabulary = 'getContainerTypes',
        relationship = 'ContainerContainerType',
        referenceClass = HoldingReference,
        widget = ReferenceWidget(
            checkbox_bound = 1,
            label = _("Container Type"),
        ),
    ),
))
schema['description'].widget.visible = True
schema['description'].schemata = 'default'

class Container(BaseContent):
    security = ClassSecurityInfo()
    displayContentsTab = False
    schema = schema

    _at_rename_after_creation = True
    def _renameAfterCreation(self, check_auto_id=False):
        from bika.lims.idserver import renameAfterCreation
        renameAfterCreation(self)

    def getContainerTypes(self):
        bsc = getToolByName(self, 'bika_setup_catalog')
        items = [('','')] + [(o.UID, o.Title) for o in
                               bsc(portal_type='ContainerType')]
        o = self.getContainerType()
        if o and o.UID() not in [i[0] for i in items]:
            items.append((o.UID(), o.Title()))
        items.sort(lambda x,y: cmp(x[1], y[1]))
        return DisplayList(list(items))

    def getPreservations(self):
        bsc = getToolByName(self, 'bika_setup_catalog')
        items = [('','')] + [(o.UID, o.Title) for o in
                               bsc(portal_type='Preservation',
                                   inactive_state = 'active')]
        o = self.getPreservation()
        if o and o.UID() not in [i[0] for i in items]:
            items.append((o.UID(), o.Title()))
        items.sort(lambda x,y: cmp(x[1], y[1]))
        return DisplayList(list(items))

registerType(Container, PROJECTNAME)
