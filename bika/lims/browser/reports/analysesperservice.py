from AccessControl import getSecurityManager
from DateTime import DateTime
from Products.CMFCore.utils import getToolByName
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import bikaMessageFactory as _
from bika.lims.browser.client import ClientSamplesView
from bika.lims.utils import formatDateQuery, formatDateParms
from bika.lims.interfaces import IReports
from plone.app.content.browser.interfaces import IFolderContentsView
from plone.app.layout.globals.interfaces import IViewView
from zope.interface import implements
import json
import plone

class AnalysesPerService(BrowserView):
    """ stuff
    """
    implements(IViewView)
    template = ViewPageTemplateFile("report_out.pt")

    def __init__(self, context, request):
        BrowserView.__init__(self, context, request)

    def __call__(self):
        # get all the data into datalines
        
        sc = getToolByName(self.context, 'bika_setup_catalog')
        pc = getToolByName(self.context, 'portal_catalog')
        rc = getToolByName(self.context, 'reference_catalog')
        self.report_content = {}
        parm_lines = {}
        parms = []
        headings = {}
        headings['header'] = _("Analyses per analysis service")
        headings['subheader'] = _("Number of analyses requested per analysis service")

        count_all = 0
        query = {'portal_type': 'Analysis'}
        if self.request.form.has_key('getClientUID'):
            client_uid = self.request.form['getClientUID']
            query['getClientUID'] = client_uid
            client = rc.lookupObject(client_uid)
            client_title = client.Title()
        else:
            client_title = 'Undefined'
        parms.append(
            { 'title': _('Client'),
             'value': client_title,
             'type': 'text'})

        date_query = formatDateQuery(self.context, 'DateRequested')
        if date_query:
            query['created'] = date_query
            requested = formatDateParms(self.context, 'DateRequested') 
        else:
            requested = 'Undefined'
        parms.append(
            { 'title': _('Requested'),
             'value': requested,
             'type': 'text'})

        date_query = formatDateQuery(self.context, 'DatePublished')
        if date_query:
            query['getDatePublished'] = date_query
            published = formatDateParms(self.context, 'DatePublished') 
        else:
            published = 'Undefined'
        parms.append(
            { 'title': _('Published'),
             'value': published,
             'type': 'text'})


        workflow = getToolByName(self.context, 'portal_workflow')
        if self.request.form.has_key('review_state'):
            query['review_state'] = self.request.form['review_state']
            review_state = workflow.getTitleForStateOnType(
                        self.request.form['review_state'], 'Analysis')
        else:
            review_state = 'Undefined'
        parms.append(
            { 'title': _('Status'),
             'value': review_state,
             'type': 'text'})

        if self.request.form.has_key('cancellation_state'):
            query['cancellation_state'] = self.request.form['cancellation_state']
            cancellation_state = workflow.getTitleForStateOnType(
                        self.request.form['cancellation_state'], 'Analysis')
        else:
            cancellation_state = 'Undefined'
        parms.append(
            { 'title': _('Active'),
             'value': cancellation_state,
             'type': 'text'})



        if self.request.form.has_key('ws_review_state'):
            query['worksheetanalysis_review_state'] = self.request.form['ws_review_state']
            ws_review_state = workflow.getTitleForStateOnType(
                        self.request.form['ws_review_state'], 'Analysis')
        else:
            ws_review_state = 'Undefined'
        parms.append(
            { 'title': _('Assigned to worksheet'),
             'value': ws_review_state,
             'type': 'text'})



        datalines = []
        for cat in sc(portal_type="AnalysisCategory",
                        sort_on='sortable_title'):
            service_data = []
            for service in sc(portal_type="AnalysisService",
                            getCategoryUID = cat.UID,
                            sort_on='sortable_title'):
                query['getServiceUID'] = service.UID
                analyses = pc(query)
                count_analyses = len(analyses)
                service_data.append([service.Title, count_analyses])
                count_all += count_analyses

            datalines.append([cat.Title, service_data])


        

        self.report_content = {
                'headings': headings,
                'parms': parms,
                'datalines': datalines,
                'total': count_all}


        return self.template()

    
