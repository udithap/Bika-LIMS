from AccessControl import ClassSecurityInfo
from Products.ATContentTypes.content import schemata
from Products.Archetypes import atapi
from Products.Archetypes.ArchetypeTool import registerType
from Products.CMFCore import permissions
from Products.CMFCore.utils import getToolByName
from Products.Five.browser import BrowserView
from bika.lims.browser.bika_listing import BikaListingView
from bika.lims.config import PROJECTNAME
from bika.lims import bikaMessageFactory as _
from plone.app.layout.globals.interfaces import IViewView
from bika.lims.content.bikaschema import BikaFolderSchema
from bika.lims.interfaces import ISampleTypes
from plone.app.content.browser.interfaces import IFolderContentsView
from plone.app.folder.folder import ATFolder, ATFolderSchema
from zope.interface.declarations import implements
from Products.CMFCore.utils import getToolByName
import json
import plone

class SampleTypesView(BikaListingView):
    implements(IFolderContentsView, IViewView)

    def __init__(self, context, request):
        super(SampleTypesView, self).__init__(context, request)
        bsc = getToolByName(context, 'bika_setup_catalog')
        self.contentsMethod = bsc
        self.contentFilter = {'portal_type': 'SampleType',
                              'sort_on': 'sortable_title'}
        self.context_actions = {_('Add'):
                                {'url': 'createObject?type_name=SampleType',
                                 'icon': '++resource++bika.lims.images/add.png'}}
        self.title = _("Sample Types")
        self.icon = "++resource++bika.lims.images/sampletype_big.png"
        self.description = ""
        self.show_sort_column = False
        self.show_select_row = False
        self.show_select_column = True
        self.pagesize = 25

        self.columns = {
            'Title': {'title': _('Sample Type'),
                      'index': 'sortable_title',},
            'Description': {'title': _('Description'),
                            'index': 'description',
                            'toggle': True},
        }

        self.review_states = [
            {'id':'all',
             'title': _('All'),
             'columns': ['Title', 'Description']},
            {'id':'active',
             'title': _('Active'),
             'contentFilter': {'inactive_state': 'active'},
             'transitions': [{'id':'deactivate'}, ],
             'columns': ['Title', 'Description']},
            {'id':'inactive',
             'title': _('Dormant'),
             'contentFilter': {'inactive_state': 'inactive'},
             'transitions': [{'id':'activate'}, ],
             'columns': ['Title', 'Description']},
        ]

    def folderitems(self):
        items = BikaListingView.folderitems(self)
        for x in range(len(items)):
            if not items[x].has_key('obj'): continue
            obj = items[x]['obj']
            items[x]['Description'] = obj.Description()
            items[x]['replace']['Title'] = "<a href='%s'>%s</a>" % \
                 (items[x]['url'], items[x]['Title'])
        return items

schema = ATFolderSchema.copy()

class SampleTypes(ATFolder):
    implements(ISampleTypes)
    displayContentsTab = False
    schema = schema

schemata.finalizeATCTSchema(schema, folderish = True, moveDiscussion = False)
atapi.registerType(SampleTypes, PROJECTNAME)

class ajax_SampleTypes(BrowserView):
    """ autocomplete data source for sample types field
        return JSON data [string,string]
        if "samplepoint" is in the request, it's expected to be a title string
        The objects returned will be filtered by samplepoint's SampleTypes.
        if no items are found, all items are returned.

        If term is a one or two letters, return items that begin with them
            If there aren't any, return items that contain them
    """
    def __call__(self):
        plone.protect.CheckAuthenticator(self.request)
        bsc = getToolByName(self.context, 'bika_setup_catalog')

        term = self.request.get('term', '').lower()

        items = bsc(portal_type = "SampleType", sort_on='sortable_title')

        if term and len(term) < 3:
            # Items that start with A or AA
            items = [s.getObject()
                     for s in items
                     if s.Title.lower().startswith(term)]
            if not items:
                # or, items that contain A or AA
                items = [s.getObject()
                         for s in items
                         if s.Title.lower().find(term) > -1]
        else:
            # or, items that contain term.
            items = [s.getObject()
                     for s in items
                     if s.Title.lower().find(term) > -1]

        samplepoint = self.request.get('samplepoint', '')
        if samplepoint and len(samplepoint) > 1:
            sp = bsc(portal_type="SamplePoint",Title=samplepoint)
            if not sp:
                return json.dumps([])
            sp = sp[0].getObject()
            new = [s for s in items if s in sp.getSampleTypes()]
            if new:
                items = new

        items = [s.Title() for s in items]
        return json.dumps(items)
