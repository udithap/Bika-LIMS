from AccessControl import ClassSecurityInfo
from Products.ATContentTypes.lib.historyaware import HistoryAwareMixin
from Products.Archetypes.public import *
from Products.Archetypes.references import HoldingReference
from Products.CMFCore.permissions import View, ModifyPortalContent
from Products.CMFCore.utils import getToolByName
from Products.Five.browser import BrowserView
from bika.lims import bikaMessageFactory as _
from bika.lims.config import PROJECTNAME
from bika.lims.browser.widgets import DurationWidget
from bika.lims.browser.fields import DurationField
from bika.lims.content.bikaschema import BikaSchema
from magnitude import mg
from zope.interface import implements
import json
import plone

schema = BikaSchema.copy() + Schema((
    DurationField('RetentionPeriod',
        required = 1,
        default_method = 'getDefaultLifetime',
        widget = DurationWidget(
            label = _("Retention Period"),
            description = _("The period for which un-preserved samples of this type can be kept before "
                            "they expire and cannot be analysed any further"),
        )
    ),
    BooleanField('Hazardous',
        default = False,
        widget = BooleanWidget(
            label = _("Hazardous"),
            description = _("Samples of this type should be treated as hazardous"),
        ),
    ),
    StringField('Prefix',
        required = True,
        widget = StringWidget(
            label = _('Sample Type Prefix'),
        ),
    ),
    StringField('Unit',
        required = 1,
        widget = StringWidget(
            label = _("Unit"),
            description = _("Sample volume is specified in this unit."),
        ),
    ),
    ReferenceField('SamplePoints',
        required = 0,
        multiValued = 1,
        allowed_types = ('SamplePoint',),
        vocabulary = 'SamplePointsVocabulary',
        relationship = 'SampleTypeSamplePoint',
        widget = ReferenceWidget(
            checkbox_bound = 1,
            label = _("Sample Points"),
            description = _("The list of sample points from which this sample "
                            "type can be collected.  If no sample points are "
                            "selected, then all sample points are available."),
        ),
    ),
))

schema['description'].schemata = 'default'
schema['description'].widget.visible = True

class SampleType(BaseContent, HistoryAwareMixin):
    security = ClassSecurityInfo()
    displayContentsTab = False
    schema = schema

    _at_rename_after_creation = True
    def _renameAfterCreation(self, check_auto_id=False):
        from bika.lims.idserver import renameAfterCreation
        renameAfterCreation(self)

    def getDefaultLifetime(self):
        """ get the default retention period """
        settings = getToolByName(self, 'bika_setup')
        return settings.getDefaultSampleLifetime()

    def getUnits(self):
        return getUnits(self)

    def SamplePointsVocabulary(self):
        from bika.lims.content.samplepoint import SamplePoints
        return SamplePoints(self, allow_blank=False)

    def setSamplePoints(self, value, **kw):
        """ For the moment, we're manually trimming the sampletype<>samplepoint
            relation to be equal on both sides, here.
            It's done strangely, because it may be required to behave strangely.
        """
        bsc = getToolByName(self, 'bika_setup_catalog')
        ## convert value to objects
        if value and type(value) == str:
            value = [bsc(UID=value)[0].getObject(),]
        elif value and type(value) in (list, tuple) and type(value[0]) == str:
            value = [bsc(UID=uid)[0].getObject() for uid in value if uid]
        ## Find all SamplePoints that were removed
        existing = self.Schema()['SamplePoints'].get(self)
        removed = existing and [s for s in existing if s not in value] or []
        added = value and [s for s in value if s not in existing] or []
        ret = self.Schema()['SamplePoints'].set(self, value)

        for sp in removed:
            sampletypes = sp.getSampleTypes()
            if self in sampletypes:
                sampletypes.remove(self)
                sp.setSampleTypes(sampletypes)

        for sp in added:
            sp.setSampleTypes(list(sp.getSampleTypes()) + [self,])

        return ret

    def getSamplePoints(self, **kw):
        return self.Schema()['SamplePoints'].get(self)

registerType(SampleType, PROJECTNAME)

def SampleTypes(self, instance=None, allow_blank=False):
    instance = instance or self
    bsc = getToolByName(instance, 'bika_setup_catalog')
    items = []
    for st in bsc(portal_type='SampleType',
                  inactive_state='active',
                  sort_on = 'sortable_title'):
        items.append((st.UID, st.Title))
    items = allow_blank and [['','']] + list(items) or list(items)
    return DisplayList(items)
