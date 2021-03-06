from Products.CMFCore.utils import getToolByName
from Products.CMFCore.permissions import View
from AccessControl import getSecurityManager
from bika.lims.permissions import AddClient
from bika.lims.permissions import CancelAndReinstate
from bika.lims.permissions import ManageAnalysisRequests
from bika.lims.browser.bika_listing import BikaListingView
from bika.lims import bikaMessageFactory as _
from bika.lims.interfaces import IClientFolder
from plone.app.content.browser.interfaces import IFolderContentsView
from Products.Five.browser import BrowserView
from zope.interface import implements
from Products.CMFCore import permissions

class ClientFolderContentsView(BikaListingView):

    implements(IFolderContentsView)

    def __init__(self, context, request):
        super(ClientFolderContentsView, self).__init__(context, request)
        self.contentFilter = {'portal_type': 'Client',
                              'sort_on': 'sortable_title'}

        self.icon = "++resource++bika.lims.images/client_big.png"
        self.title = _("Clients")
        self.description = ""
        self.show_sort_column = False
        self.show_select_row = False
        self.show_select_all_checkbox = False
        self.show_select_column = False
        self.pagesize = 25
        request.set('disable_border', 1)

        self.columns = {
            'title': {'title': _('Name'), 'index': 'sortable_title'},
            'EmailAddress': {'title': _('Email Address')},
            'Phone': {'title': _('Phone')},
            'Fax': {'title': _('Fax')},
        }

        self.review_states = [
            {'id':'all',
             'title': _('All'),
             'transitions': [{'id':'empty'}, ], # none
             'columns':['title',
                        'EmailAddress',
                        'Phone',
                        'Fax', ]
             },
        ]

        mtool = getToolByName(self.context, 'portal_membership')
        if mtool.checkPermission(CancelAndReinstate, self.context):
            self.show_select_column = True
            self.review_states[0]['transitions'] = [] # all
            self.review_states.append(
                {'id':'active',
                 'title': _('Active'),
                 'contentFilter': {'inactive_state': 'active'},
                 'transitions': [{'id':'deactivate'}, ],
                 'columns':['title',
                            'EmailAddress',
                            'Phone',
                            'Fax', ]
                 })
            self.review_states.append(
                {'id':'inactive',
                 'title': _('Dormant'),
                 'contentFilter': {'inactive_state': 'inactive'},
                 'transitions': [{'id':'activate'}, ],
                 'columns':['title',
                            'EmailAddress',
                            'Phone',
                            'Fax', ]
                 })

    def __call__(self):
        self.context_actions = {}
        mtool = getToolByName(self.context, 'portal_membership')
        if (mtool.checkPermission(AddClient, self.context)):
            self.context_actions['Add'] = \
                {'url': 'createObject?type_name=Client',
                 'icon': '++resource++bika.lims.images/add.png'}
        return super(ClientFolderContentsView, self).__call__()

    def getClientList(self, contentFilter):

        ## Only show clients to which we have Manage AR rights.
        ## (ritamo only sees Happy Hills).

        mtool = getToolByName(self.context, 'portal_membership')

        clients = []
        for client in self.context.objectValues("Client"):
            if not mtool.checkPermission(ManageAnalysisRequests, client):
                continue
            clients.append(client)
        return clients

    def folderitems(self):
        self.contentsMethod = self.getClientList
        items = BikaListingView.folderitems(self)
        for x in range(len(items)):
            if not items[x].has_key('obj'): continue
            obj = items[x]['obj']

            items[x]['replace']['title'] = "<a href='%s'>%s</a>"%\
                 (items[x]['url'], items[x]['title'])

            items[x]['EmailAddress'] = obj.getEmailAddress()
            items[x]['replace']['EmailAddress'] = "<a href='%s'>%s</a>"%\
                     ('mailto:%s' % obj.getEmailAddress(),
                      obj.getEmailAddress())
            items[x]['Phone'] = obj.getPhone()
            items[x]['Fax'] = obj.getFax()

        return items
