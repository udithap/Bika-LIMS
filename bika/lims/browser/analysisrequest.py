from Products.CMFCore.utils import getToolByName
from AccessControl import getSecurityManager
from DateTime import DateTime
from Products.Archetypes.config import REFERENCE_CATALOG
from Products.Archetypes.public import DisplayList
from Products.CMFCore.WorkflowCore import WorkflowException
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import PMF
from bika.lims import logger
from bika.lims import bikaMessageFactory as _
from bika.lims.browser.analyses import AnalysesView
from bika.lims.browser.bika_listing import BikaListingView
from bika.lims.browser.bika_listing import  WorkflowAction
from bika.lims.browser.publish import Publish
from bika.lims.browser.sample import SamplePartitionsView
from bika.lims.config import POINTS_OF_CAPTURE
from bika.lims.permissions import EditAR
from bika.lims.permissions import EditFieldResults
from bika.lims.permissions import EditResults
from bika.lims.permissions import ManageSamples
from bika.lims.permissions import PreserveSample
from bika.lims.permissions import ResultsNotRequested
from bika.lims.permissions import SampleSample
from bika.lims.permissions import ViewResults
from bika.lims.utils import getUsers
from bika.lims.utils import isActive
from bika.lims.utils import TimeOrDate
from bika.lims.utils import pretty_user_name_or_id
from bika.lims.subscribers import skip
from bika.lims.subscribers import doActionFor
from plone.app.content.browser.interfaces import IFolderContentsView
from plone.app.layout.globals.interfaces import IViewView
from zope.interface import implements, alsoProvides
from zope.i18n.locales import locales
import App
import json
import plone
import re

class AnalysisRequestWorkflowAction(WorkflowAction):
    """Workflow actions taken in AnalysisRequest context.

        Sample context workflow actions also redirect here
        Applies to
            Analysis objects
            SamplePartition objects
    """
    def __call__(self):
        form = self.request.form
        plone.protect.CheckAuthenticator(form)
        workflow = getToolByName(self.context, 'portal_workflow')
        rc = getToolByName(self.context, REFERENCE_CATALOG)
        translate = self.context.translation_service.translate
        action, came_from = WorkflowAction._get_form_workflow_action(self)
        checkPermission = self.context.portal_membership.checkPermission

        # calcs.js has kept item_data and form input interim values synced,
        # so the json strings from item_data will be the same as the form values
        item_data = {}
        if 'item_data' in form:
            if type(form['item_data']) == list:
                for i_d in form['item_data']:
                    for i, d in json.loads(i_d).items():
                        item_data[i] = d
            else:
                item_data = json.loads(form['item_data'])

        ## Analyses added or removed
        if action == "save_button":
            ar = self.context
            sample = ar.getSample()
            objects = WorkflowAction._get_selected_items(self)
            form_parts = json.loads(self.request.form['parts'])
            if not form_parts:
                message = _('No changes made.')
            else:
                new_analyses = ar.setAnalyses(objects.keys(),
                                              prices = form['Price'][0])

                # XXX

                # stopgap - ignore selected values ; assign first partition
                # to new analyses.  Form interface doesn't yet support
                # selection of partition - AR Add and AR Edit will get some
                # additional functionality for this, soon.
                first_part = sample.objectValues("SamplePartition")[0]
                for a in new_analyses:
                    a.setSamplePartition(first_part)

                message = translate(PMF("Changes saved."))

            self.context.plone_utils.addPortalMessage(message, 'info')
            self.destination_url = self.context.absolute_url()
            self.request.response.redirect(self.destination_url)
            return

        ## Partition Preservation
        # the partition table shown in AR and Sample views sends it's
        # action button submits here.
        elif action == "preserved":
            objects = WorkflowAction._get_selected_items(self)
            transitioned = []
            for obj_uid, obj in objects.items():
                part = obj
                # can't transition inactive items
                if workflow.getInfoFor(part, 'inactive_state', '') == 'inactive':
                    continue
                if not checkPermission(PreserveSample, part):
                    continue

                # grab this object's Preserver and DatePreserved from the form
                Preserver = form['getPreserver'][0][obj_uid].strip()
                Preserver = Preserver and Preserver or ''
                DatePreserved = form['getDatePreserved'][0][obj_uid].strip()
                DatePreserved = DatePreserved and DateTime(DatePreserved) or ''

                # write them to the sample
                part.setPreserver(Preserver)
                part.setDatePreserved(DatePreserved)

                # transition the object if both values are present
                if Preserver and DatePreserved:
                    workflow.doActionFor(part, 'preserved')
                    transitioned.append(part.id)

                part.reindexObject()
                part.aq_parent.reindexObject()

            message = None
            if len(transitioned) > 1:
                message = _('${items} are waiting to be received.',
                            mapping = {'items': ', '.join(transitioned)})
                message = self.context.translate(message)
                self.context.plone_utils.addPortalMessage(message, 'info')
            elif len(transitioned) == 1:
                message = _('${item} is waiting to be received.',
                            mapping = {'item': ', '.join(transitioned)})
                message = self.context.translate(message)
                self.context.plone_utils.addPortalMessage(message, 'info')
            if not message:
                message = _('No changes made.')
                message = self.context.translate(message)
                self.context.plone_utils.addPortalMessage(message, 'info')
            self.destination_url = self.request.get_header("referer",
                                   self.context.absolute_url())
            self.request.response.redirect(self.destination_url)

        elif action == "sampled":
            objects = WorkflowAction._get_selected_items(self)
            transitioned = {'to_be_preserved':[], 'sample_due':[]}
            for obj_uid, obj in objects.items():
                part = obj
                sample = part.aq_parent
                # can't transition inactive items
                if workflow.getInfoFor(part, 'inactive_state', '') == 'inactive':
                    continue
                if not checkPermission(SampleSample, part):
                    continue

                # grab this object's Sampler and DateSampled from the form
                Sampler = form['getSampler'][0][obj_uid].strip()
                Sampler = Sampler and Sampler or ''
                DateSampled = form['getDateSampled'][0][obj_uid].strip()
                DateSampled = DateSampled and DateTime(DateSampled) or ''

                # write them to the partition
                part.setSampler(Sampler)
                part.setDateSampled(DateSampled)

                # transition the object if both values are present
                if Sampler and DateSampled:
                    workflow.doActionFor(part, 'sampled')
                    new_state = workflow.getInfoFor(part, 'review_state')
                    transitioned[new_state].append(part.id)

                part.reindexObject()
                part.aq_parent.reindexObject()

            message = None
            for state in transitioned:
                t = transitioned[state]
                if len(t) > 1:
                    if state == 'to_be_preserved':
                        message = _('${items} are waiting for preservation.',
                                    mapping = {'items': ', '.join(t)})
                    else:
                        message = _('${items} are waiting to be received.',
                                    mapping = {'items': ', '.join(t)})
                    message = self.context.translate(message)
                    self.context.plone_utils.addPortalMessage(message, 'info')
                elif len(t) == 1:
                    if state == 'to_be_preserved':
                        message = _('${item} is waiting for preservation.',
                                    mapping = {'item': ', '.join(t)})
                    else:
                        message = _('${item} is waiting to be received.',
                                    mapping = {'item': ', '.join(t)})
                    message = self.context.translate(message)
                    self.context.plone_utils.addPortalMessage(message, 'info')
            if not message:
                message = _('No changes made.')
                message = self.context.translate(message)
                self.context.plone_utils.addPortalMessage(message, 'info')
            self.destination_url = self.request.get_header("referer",
                                   self.context.absolute_url())
            self.request.response.redirect(self.destination_url)

        ## submit
        elif action == 'submit' and self.request.form.has_key("Result"):
            if not isActive(self.context):
                message = translate(_('Item is inactive.'))
                self.context.plone_utils.addPortalMessage(message, 'info')
                self.request.response.redirect(self.context.absolute_url())
                return

            selected_analyses = WorkflowAction._get_selected_items(self)
            results = {}
            hasInterims = {}

            # check that the form values match the database
            # save them if not.
            for uid, result in self.request.form['Result'][0].items():
                # if the AR has ReportDryMatter set, get dry_result from form.
                dry_result = ''
                if hasattr(self.context, 'getReportDryMatter') \
                   and self.context.getReportDryMatter():
                    for k, v in self.request.form['ResultDM'][0].items():
                        if uid == k:
                            dry_result = v
                            break
                if uid in selected_analyses:
                    analysis = selected_analyses[uid]
                else:
                    analysis = rc.lookupObject(uid)
                if not analysis:
                    # ignore result if analysis object no longer exists
                    continue
                if not checkPermission(EditResults, analysis) \
                   and not checkPermission(EditFieldResults, analysis):
                    mtool = getToolByName(self.context, 'portal_membership')
                    username = mtool.getAuthenticatedMember().getUserName()
                    path = "/".join(self.context.getPhysicalPath())
                    logger.info("Changes no longer allowed (user: %s, object: %s)" % \
                                (username, path))
                    continue
                results[uid] = result
                service = analysis.getService()
                interimFields = item_data[uid]
                if len(interimFields) > 0:
                    hasInterims[uid] = True
                else:
                    hasInterims[uid] = False
                service_unit = service.getUnit() and service.getUnit() or ''
                retested = form.has_key('retested') and form['retested'].has_key(uid)
                # Don't save uneccessary things
                if analysis.getInterimFields() != interimFields or \
                   analysis.getRetested() != retested:
                    analysis.edit(
                        InterimFields = interimFields,
                        Retested = retested)
                # save results separately, otherwise capture date is rewritten
                if analysis.getResult() != result or \
                   analysis.getResultDM() != dry_result:
                    analysis.edit(
                        ResultDM = dry_result,
                        Result = result)

            # discover which items may be submitted
            # guard_submit does a lot of the same stuff, too.
            submissable = []
            for uid, analysis in selected_analyses.items():
                if uid not in results or not results[uid]:
                    continue
                can_submit = True
                for dependency in analysis.getDependencies():
                    dep_state = workflow.getInfoFor(dependency, 'review_state')
                    if hasInterims[uid]:
                        if dep_state in ('to_be_sampled', 'to_be_preserved',
                                         'sample_due', 'sample_received',
                                         'attachment_due', 'to_be_verified',):
                            can_submit = False
                            break
                    else:
                        if dep_state in ('to_be_sampled', 'to_be_preserved',
                                         'sample_due', 'sample_received',):
                            can_submit = False
                            break
                if can_submit and analysis not in submissable:
                    submissable.append(analysis)

            # and then submit them.
            for analysis in submissable:
                doActionFor(analysis, 'submit')

            message = translate(PMF("Changes saved."))
            self.context.plone_utils.addPortalMessage(message, 'info')
            if checkPermission(EditResults, self.context):
                self.destination_url = self.context.absolute_url() + "/manage_results"
            else:
                self.destination_url = self.context.absolute_url()
            self.request.response.redirect(self.destination_url)

        ## publish
        elif action in ('prepublish', 'publish', 'republish'):
            if not isActive(self.context):
                message = translate(_('Item is inactive.'))
                self.context.plone_utils.addPortalMessage(message, 'info')
                self.request.response.redirect(self.context.absolute_url())
                return

            # publish entire AR.
            self.context.setDatePublished(DateTime())
            transitioned = Publish(self.context,
                                   self.request,
                                   action,
                                   [self.context, ])()
            if len(transitioned) == 1:
                message = translate('${items} published.',
                                    mapping = {'items': ', '.join(transitioned)})
            else:
                message = translate(_("No items were published"))
            self.context.plone_utils.addPortalMessage(message, 'info')
            self.destination_url = self.request.get_header("referer",
                                   self.context.absolute_url())
            self.request.response.redirect(self.destination_url)

        ## verify
        elif action == 'verify':
            # default bika_listing.py/WorkflowAction, but then go to view screen.
            self.destination_url = self.context.absolute_url()
            WorkflowAction.__call__(self)

        else:
            # default bika_listing.py/WorkflowAction for other transitions
            WorkflowAction.__call__(self)

class AnalysisRequestViewView(BrowserView):
    """ AR View form
        The AR fields are printed in a table, using analysisrequest_view.py
    """

    implements(IViewView)
    template = ViewPageTemplateFile("templates/analysisrequest_view.pt")
    header_table = ViewPageTemplateFile("templates/header_table.pt")

    def __init__(self, context, request):
        super(AnalysisRequestViewView, self).__init__(context, request)
        self.icon = "++resource++bika.lims.images/analysisrequest_big.png"
        self.TimeOrDate = TimeOrDate

    def __call__(self):
        form = self.request.form
        ar = self.context
        bsc = getToolByName(self.context, 'bika_setup_catalog')
        checkPermission = self.context.portal_membership.checkPermission
        getAuthenticatedMember = self.context.portal_membership.getAuthenticatedMember
        workflow = getToolByName(self.context, 'portal_workflow')
        props = getToolByName(self.context, 'portal_properties').bika_properties
        datepicker_format = props.getProperty('datepicker_format')

        ## Create header_table data rows
        sample = self.context.getSample()
        sp = sample.getSamplePoint()
        st = sample.getSampleType()

        contact = self.context.getContact()
        ccs = ["<a href='%s'>%s</a>"%(contact.absolute_url(), contact.Title()),]
        for cc in self.context.getCCContact():
            ccs.append("<a href='%s'>%s</a>"%(cc.absolute_url(), cc.Title()),)
        emails = self.context.getCCEmails()
        if type(emails) == str:
            emails = [emails,]
        for cc in emails:
            ccs.append("<a href='mailto:%s'>%s</a>"%(cc, cc))

        # Some sample fields are editable here
        if workflow.getInfoFor(sample, 'cancellation_state') == "cancelled":
            allow_sample_edit = False
        else:
            edit_states = ['to_be_sampled', 'to_be_preserved', 'sample_due']
            allow_sample_edit = checkPermission(ManageSamples, sample) \
                and workflow.getInfoFor(sample, 'review_state') in edit_states

        self.header_columns = 3
        self.header_rows = [
            {'id': 'SampleID',
             'title': _('Sample ID'),
             'allow_edit': False,
             'value': "<a href='%s'>%s</a>"%(sample.absolute_url(), sample.id),
             'condition':True,
             'type': 'text'},
            {'id': 'ClientSampleID',
             'title': _('Client SID'),
             'allow_edit': True,
             'value': sample.getClientSampleID(),
             'condition':True,
             'type': 'text'},
            {'id': 'Contact',
             'title': "<a href='#' id='open_cc_browser'>%s</a>" % _('Contact Person'),
             'allow_edit': False,
             'value': "; ".join(ccs),
             'condition':True,
             'type': 'text'},
            {'id': 'ClientReference',
             'title': _('Client Reference'),
             'allow_edit': True,
             'value': sample.getClientReference(),
             'condition':True,
             'type': 'text'},
            {'id': 'ClientOrderNumber',
             'title': _('Client Order'),
             'allow_edit': True,
             'value': self.context.getClientOrderNumber(),
             'condition':True,
             'type': 'text'},
            {'id': 'SampleType',
             'title': _('Sample Type'),
             'allow_edit': allow_sample_edit,
             'value': st and st.Title() or '',
             'condition':True,
             'type': 'text',
             'required': True},
            {'id': 'SamplePoint',
             'title': _('Sample Point'),
             'allow_edit': allow_sample_edit,
             'value': sp and sp.Title() or '',
             'condition':True,
             'type': 'text'},
            {'id': 'Creator',
             'title': PMF('Creator'),
             'allow_edit': False,
             'value': pretty_user_name_or_id(self.context, self.context.Creator()),
             'condition':True,
             'type': 'text'},
            {'id': 'DateCreated',
             'title': PMF('Date Created'),
             'allow_edit': False,
             'value': self.context.created(),
             'condition':True,
             'formatted_value': TimeOrDate(self.context, self.context.created()),
             'type': 'text'},
            {'id': 'SamplingDate',
             'title': _('Sampling Date'),
             'allow_edit': allow_sample_edit,
             'value': sample.getSamplingDate().strftime(datepicker_format),
             'formatted_value': TimeOrDate(self.context, self.context.getSamplingDate()),
             'condition':True,
             'class': 'datepicker',
             'type': 'text'},
            {'id': 'DateReceived',
             'title': _('Date Received'),
             'allow_edit': False,
             'value': self.context.getDateReceived(),
             'formatted_value': TimeOrDate(self.context, self.context.getDateReceived()),
             'condition':True,
             'type': 'text'},
            {'id': 'Composite',
             'title': _('Composite'),
             'allow_edit': allow_sample_edit,
             'value': sample.getComposite(),
             'condition':True,
             'type': 'boolean'},
            {'id': 'InvoiceExclude',
             'title': _('Invoice Exclude'),
             'allow_edit': True,
             'value': self.context.getInvoiceExclude(),
             'condition':True,
             'type': 'boolean'},
            {'id': 'ReportDryMatter',
             'title': _('Report as Dry Matter'),
             'allow_edit': allow_sample_edit,
             'value': self.context.getReportDryMatter(),
             'condition':self.context.bika_setup.getDryMatterService(),
             'type': 'boolean'},
        ]
        self.header_buttons = [{'name':'save_button', 'title':_('Save')}]

        ## handle_header table submit
        if 'save_button' in form:
            message = None
            values = {}
            for row in [r for r in self.header_rows if r['allow_edit']]:
                value = form.get(row['id'], '')

                if row['id'] == 'SampleType':
                    if not value:
                        message = _('Sample Type is required')
                        break
                    if not bsc(portal_type = 'SampleType', title = value):
                        message = _("${sampletype} is not a valid sample type",
                                    mapping={'sampletype':value})
                        break

                if row['id'] == 'SamplePoint':
                    if value and \
                       not bsc(portal_type = 'SamplePoint', title = value):
                        message = _("${samplepoint} is not a valid sample point",
                                    mapping={'sampletype':value})
                        break

                values[row['id']] = value

            # boolean - checkboxes are present, or not present in form.
            for row in [r for r in self.header_rows if r.get('type', '') == 'boolean']:
                values[row['id']] = row['id'] in form

            if not message:
                self.context.edit(**values)
                self.context.reindexObject()
                sample.edit(**values)
                sample.reindexObject()
                message = PMF("Changes saved.")

            self.context.plone_utils.addPortalMessage(message, 'info')
            # we need to start the request again, to regenerate header
            self.request.RESPONSE.redirect(self.context.absolute_url())
            return

        ## Create Partitions View for this ARs sample
        p = SamplePartitionsView(self.context.getSample(), self.request)
        p.show_column_toggles = False
        self.parts = p.contents_table()

        ## Create Field and Lab Analyses tables
        self.tables = {}
        for poc in POINTS_OF_CAPTURE:
            if self.context.getAnalyses(getPointOfCapture = poc):
                t = AnalysesView(ar, self.request, getPointOfCapture = poc)
                t.allow_edit = True
                t.form_id = "%s_analyses" % poc
                t.review_states[0]['transitions'] = [{'id':'submit'},
                                                     {'id':'retract'},
                                                     {'id':'verify'}]
                t.show_workflow_action_buttons = True
                t.show_select_column = True
                if getSecurityManager().checkPermission(EditFieldResults, self.context) \
                   and poc == 'field':
                    t.review_states[0]['columns'].remove('DueDate')
                self.tables[POINTS_OF_CAPTURE.getValue(poc)] = t.contents_table()
        return self.template()

    def tabindex(self):
        i = 0
        while True:
            i += 1
            yield i

    def now(self):
        return DateTime()

    def arprofiles(self):
        """ Return applicable client and Lab ARProfile records
        """
        translate = self.context.translate
        profiles = []
        for profile in self.context.objectValues("ARProfile"):
            if isActive(profile):
                profiles.append((profile.Title(), profile))
        for profile in self.context.bika_setup.bika_arprofiles.objectValues("ARProfile"):
            if isActive(profile):
                profiles.append((translate(_('Lab')) + ": " + profile.Title(), profile))
        return profiles

    def artemplates(self):
        """ Return applicable client and Lab ARTemplate records
        """
        translate = self.context.translate
        templates = []
        for template in self.context.objectValues("ARTemplate"):
            if isActive(template):
                templates.append((template.Title(), template))
        for template in self.context.bika_setup.bika_arprofiles.objectValues("ARTemplate"):
            if isActive(template):
                templates.append((translate(_('Lab')) + ": " + template.Title(), template))
        return templates

    def SelectedServices(self):
        """ return information about services currently selected in the
            context AR.
            [[PointOfCapture, category uid, service uid],
             [PointOfCapture, category uid, service uid], ...]
        """
        pc = getToolByName(self.context, 'portal_catalog')
        res = []
        for analysis in pc(portal_type = "Analysis",
                           getRequestID = self.context.RequestID):
            analysis = analysis.getObject()
            service = analysis.getService()
            res.append([service.getPointOfCapture(),
                        service.getCategoryUID(),
                        service.UID()])
        return res

    def Categories(self):
        """ Dictionary keys: poc
            Dictionary values: (Category UID,category Title)
        """
        bsc = getToolByName(self.context, 'bika_setup_catalog')
        cats = {}
        restricted = [u.UID() for u in self.context.getRestrictedCategories()]
        for service in bsc(portal_type = "AnalysisService",
                           inactive_state = 'active'):
            cat = (service.getCategoryUID, service.getCategoryTitle)
            if restricted and cat[0] not in restricted:
                continue
            poc = service.getPointOfCapture
            if not cats.has_key(poc): cats[poc] = []
            if cat not in cats[poc]:
                cats[poc].append(cat)
        return cats

    def DefaultCategories(self):
        """ Used in AR add context, to return list of UIDs for
        automatically-expanded categories.
        """
        cats = self.context.getDefaultCategories()
        return [cat.UID() for cat in cats]

    def getDefaultSpec(self):
        """ Returns 'lab' or 'client' to set the initial value of the
            specification radios
        """
        mt = getToolByName(self.context, 'portal_membership')
        pg = getToolByName(self.context, 'portal_groups')
        member = mt.getAuthenticatedMember()
        member_groups = [pg.getGroupById(group.id).getGroupName() \
                         for group in pg.getGroupsByUserId(member.id)]
        default_spec = ('Clients' in member_groups) and 'client' or 'lab'
        return default_spec

    def getARProfileTitle(self):
        """Grab the context's current ARProfile Title if any
        """
        return self.context.getProfile() and \
               self.context.getProfile().Title() or ''

    def getARTemplateTitle(self):
        """Grab the context's current ARTemplate Title if any
        """
        return self.context.getTemplate() and \
               self.context.getTemplate().Title() or ''

    def get_requested_analyses(self):
        ##
        ##title=Get requested analyses
        ##
        result = []
        cats = {}
        for analysis in self.context.getAnalyses(full_objects = True):
            if analysis.review_state == 'not_requested':
                continue
            service = analysis.getService()
            category_name = service.getCategoryTitle()
            if not category_name in cats:
                cats[category_name] = {}
            cats[category_name][analysis.Title()] = analysis

        cat_keys = cats.keys()
        cat_keys.sort(lambda x, y:cmp(x.lower(), y.lower()))
        for cat_key in cat_keys:
            analyses = cats[cat_key]
            analysis_keys = analyses.keys()
            analysis_keys.sort(lambda x, y:cmp(x.lower(), y.lower()))
            for analysis_key in analysis_keys:
                result.append(analyses[analysis_key])
        return result

    def get_analyses_not_requested(self):
        ##
        ##title=Get analyses which have not been requested by the client
        ##

        result = []
        for analysis in self.context.getAnalyses():
            if analysis.review_state == 'not_requested':
                result.append(analysis)

        return result

    def get_analysisrequest_verifier(self, analysisrequest):
        ## Script (Python) "get_analysisrequest_verifier"
        ##bind container=container
        ##bind context=context
        ##bind namespace=
        ##bind script=script
        ##bind subpath=traverse_subpath
        ##parameters=analysisrequest
        ##title=Get analysis workflow states
        ##

        ## get the name of the member who last verified this AR
        ##  (better to reverse list and get first!)

        wtool = getToolByName(self.context, 'portal_workflow')
        mtool = getToolByName(self.context, 'portal_membership')

        verifier = None
        try:
            review_history = wtool.getInfoFor(analysisrequest, 'review_history')
        except:
            return 'access denied'

        review_history = [review for review in review_history if review.get('action', '')]
        if not review_history:
            return 'no history'
        for items in  review_history:
            action = items.get('action')
            if action != 'verify':
                continue
            actor = items.get('actor')
            member = mtool.getMemberById(actor)
            if not member:
                verifier = actor
                continue
            verifier = member.getProperty('fullname')
            if verifier is None or verifier == '':
                verifier = actor
        return verifier


class AnalysisRequestAddView(AnalysisRequestViewView):
    """ The main AR Add form
    """
    implements(IViewView)
    template = ViewPageTemplateFile("templates/analysisrequest_edit.pt")

    def __init__(self, context, request):
        AnalysisRequestViewView.__init__(self, context, request)
        self.came_from = "add"
        self.can_edit_sample = True
        self.can_edit_ar = True
        self.DryMatterService = self.context.bika_setup.getDryMatterService()
        request.set('disable_plone.rightcolumn', 1)

        self.col_count = 6

    def __call__(self):
        return self.template()

    def partitioned_services(self):
        bsc = getToolByName(self.context, 'bika_setup_catalog')
        ps = []
        for service in bsc(portal_type='AnalysisService'):
            service = service.getObject()
            if service.getPartitionSetup() \
               or service.getSeparate():
                ps.append(service.UID())
        return json.dumps(ps)

    def listProfiles(self):
        ## List of selected services for each ARProfile
        profiles = {}
        client = self.context.portal_type == 'AnalysisRequest' \
            and self.context.aq_parent or self.context
        for context in (client, self.context.bika_setup.bika_arprofiles):
            for profile in [p for p in context.objectValues("ARProfile")
                            if isActive(p)]:
                slist = {}
                profile_services = profile.getService()
                if type(profile_services) not in (list, tuple):
                    profile_services = [profile_services, ]
                for p_service in profile_services:
                    key = "%s_%s" % (p_service.getPointOfCapture(),
                                     p_service.getCategoryUID())
                    if key in slist:
                        slist[key].append(p_service.UID())
                    else:
                        slist[key] = [p_service.UID(), ]

                title = context == self.context.bika_setup.bika_arprofiles \
                    and self.context.translate(_('Lab')) + ": " + profile.Title() \
                    or profile.Title()

                p_dict = {
                    'UID':profile.UID(),
                    'Title':title,
                    'Services':slist,
                }
                profiles[profile.UID()] = p_dict
        return json.dumps(profiles)

    def listTemplates(self):
        ## parameters for all ARTemplates
        templates = {}
        client = self.context.portal_type == 'AnalysisRequest' \
            and self.context.aq_parent or self.context
        for context in (client, self.context.bika_setup.bika_arprofiles):
            for template in [t for t in context.objectValues("ARTemplate")
                             if isActive(t)]:
                title = context == self.context.bika_setup.bika_arprofiles \
                    and self.context.translate(_('Lab')) + ": " + template.Title() \
                    or template.Title()
                sp_title = template.getSamplePoint()
                st_title = template.getSampleType()
                profile = template.getARProfile()
                t_dict = {
                    'UID':template.UID(),
                    'Title':template.Title(),
                    'ARProfile':profile and profile.UID() or '',
                    'SamplePoint':sp_title,
                    'SampleType':st_title,
                    'ReportDryMatter':template.getReportDryMatter(),
                }
                templates[template.UID()] = t_dict
        return json.dumps(templates)

class AnalysisRequestAnalysesView(BikaListingView):
    implements(IFolderContentsView, IViewView)

    template = ViewPageTemplateFile("templates/analysisrequest_analyses.pt")

    def __init__(self, context, request):
        """
        """

        super(AnalysisRequestAnalysesView, self).__init__(context, request)
        bsc = getToolByName(context, 'bika_setup_catalog')
        self.contentsMethod = bsc
        self.contentFilter = {'portal_type': 'AnalysisService',
                              'sort_on': 'sortable_title',
                              'inactive_state': 'active',}
        self.context_actions = {}
        self.icon = "++resource++bika.lims.images/analysisrequest_big.png"
        self.title = self.context.Title()
        self.show_sort_column = False
        self.show_select_row = False
        self.show_select_column = True
        self.show_select_all_checkbox = False
        self.pagesize = 1000
        analyses = self.context.getAnalyses()
        self.analyses = dict(
            [(x.getObject().getServiceUID(), x.getObject()) for x in analyses]
        )
        self.selected = [x.getObject().getServiceUID() for x in analyses]

        self.columns = {
            'Title': {'title': _('Service'),
                      'index': 'sortable_title',
                      'sortable': False,},
            'Keyword': {'title': _('Keyword'),
                        'index': 'getKeyword',
                        'sortable': False,},
            'Price': {'title': _('Price'),
                      'sortable': False,},
            'Method': {'title': _('Method'),
                       'sortable': False,},
            'Partition': {'title': _('Partition'),
                          'sortable': False,},
            'Container': {'title': _('Container'),
                          'sortable': False,},
            'Preservation': {'title': _('Preservation'),
                             'sortable': False,},
        }

        self.review_states = [
            {'id':'all',
             'title': _('All'),
             'columns': ['Title',
                         'Price',
                         'Keyword',
                         'Method',
                         'Partition',
                         'Container',
                         'Preservation'
                         ],
             'transitions': [{'id':'empty'}, ], # none
             'custom_actions':[{'id': 'save_button', 'title': _('Save')}, ]
             },
        ]

    def folderitems(self):
        self.categories = []

        mtool = getToolByName(self.context, 'portal_membership')
        member = mtool.getAuthenticatedMember()
        roles = member.getRoles()
        can_edit_price = 'LabManager' in roles or 'Manager' in roles
        self.allow_edit = can_edit_price

        items = BikaListingView.folderitems(self)

        for x in range(len(items)):
            if not items[x].has_key('obj'): continue
            obj = items[x]['obj']

            cat = obj.getCategoryTitle()
            items[x]['category'] = cat
            if cat not in self.categories:
                self.categories.append(cat)

            items[x]['selected'] = items[x]['uid'] in self.selected

            items[x]['class']['Title'] = 'service_title'
            items[x]['Keyword'] = obj.getKeyword()

            calculation = obj.getCalculation()
            items[x]['Calculation'] = calculation and calculation.Title()

            method = obj.getMethod()
            items[x]['Method'] = method and method.Title() or ''

            locale = locales.getLocale('en')
            currency = self.context.bika_setup.getCurrency()
            symbol = locale.numbers.currencies[currency].symbol
            items[x]['before']['Price'] = symbol
            items[x]['Price'] = obj.getPrice()
            items[x]['allow_edit'] = ['Price', ]
            items[x]['class']['Price'] = 'nowrap'

            if obj.UID() in self.analyses:
                part = self.analyses[obj.UID()].getSamplePartition()
                part = part and part or obj
                items[x]['Partition'] = part.Title()
                container = part.getContainer()
                items[x]['Container'] = container and container.Title() or ''
                preservation = part.getPreservation()
                items[x]['Preservation'] = preservation and preservation.Title() or ''
            else:
                items[x]['Partition'] = ''
                items[x]['Container'] = ''
                items[x]['Preservation'] = ''

            after_icons = ''
            if obj.getAccredited():
                after_icons += "<img\
                src='++resource++bika.lims.images/accredited.png'\
                title='%s'>"%(_("Accredited"))
            if obj.getReportDryMatter():
                after_icons += "<img src='++resource++bika.lims.images/dry.png'\
                title='%s'>"%(_("Can be reported as dry matter"))
            if obj.getAttachmentOption() == 'r':
                after_icons += "<img\
                src='++resource++bika.lims.images/attach_reqd.png'\
                title='%s'>"%(_("Attachment required"))
            if obj.getAttachmentOption() == 'n':
                after_icons += "<img\
                src='++resource++bika.lims.images/attach_no.png'\
                title='%s'>"%(_('Attachment not permitted'))
            if after_icons:
                items[x]['after']['Title'] = after_icons

        self.categories.sort()
        return items

class AnalysisRequestManageResultsView(AnalysisRequestViewView):
    implements(IViewView)
    template = ViewPageTemplateFile("templates/analysisrequest_manage_results.pt")

    def __call__(self):
        ar = self.context
        workflow = getToolByName(ar, 'portal_workflow')

        if workflow.getInfoFor(ar, 'cancellation_state') == "cancelled":
            self.request.response.redirect(ar.absolute_url())
        elif not(getSecurityManager().checkPermission(EditResults, ar)):
            self.request.response.redirect(ar.absolute_url())
        else:
            self.tables = {}
            for poc in POINTS_OF_CAPTURE:
                if self.context.getAnalyses(getPointOfCapture = poc):
                    t = AnalysesView(ar,
                                     self.request,
                                     getPointOfCapture = poc,
                                     sort_on = 'getServiceTitle')
                    t.form_id = "ar_manage_results_%s" % poc
                    t.allow_edit = True
                    t.review_states[0]['transitions'] = [{'id':'submit'},
                                                         {'id':'retract'},
                                                         {'id':'verify'}]
                    t.show_select_column = True
                    self.tables[POINTS_OF_CAPTURE.getValue(poc)] = t.contents_table()
            return self.template()

class AnalysisRequestResultsNotRequestedView(AnalysisRequestManageResultsView):
    implements(IViewView)
    template = ViewPageTemplateFile("templates/analysisrequest_analyses_not_requested.pt")

    def __call__(self):
        ar = self.context
        workflow = getToolByName(ar, 'portal_workflow')

        if workflow.getInfoFor(ar, 'cancellation_state') == "cancelled":
            self.request.response.redirect(ar.absolute_url())
        elif not(getSecurityManager().checkPermission(ResultsNotRequested, ar)):
            self.request.response.redirect(ar.absolute_url())
        else:
            return self.template()

class AnalysisRequestSelectCCView(BikaListingView):

    template = ViewPageTemplateFile("templates/analysisrequest_select_cc.pt")

    def __init__(self, context, request):
        super(AnalysisRequestSelectCCView, self).__init__(context, request)
        self.icon = "++resource++bika.lims.images/contact_big.png"
        self.title = _("Contacts to CC")
        self.description = _("Select the contacts that will receive analysis results for this request.")
        c = context.portal_type == 'AnalysisRequest' and context.aq_parent or context
        self.contentFilter = {'portal_type': 'Contact',
                              'sort_on':'sortable_title',
                              'inactive_state': 'active',
                              'path': {"query": "/".join(c.getPhysicalPath()),
                                       "level" : 0 }
                              }

        self.show_sort_column = False
        self.show_select_row = False
        self.show_workflow_action_buttons = True
        self.show_select_column = True
        self.pagesize = 25

        request.set('disable_border', 1)

        self.columns = {
            'Fullname': {'title': _('Full Name'),
                         'index': 'getFullname'},
            'EmailAddress': {'title': _('Email Address')},
            'BusinessPhone': {'title': _('Business Phone')},
            'MobilePhone': {'title': _('Mobile Phone')},
        }
        self.review_states = [
            {'id':'all',
             'title': _('All'),
             'columns': ['Fullname',
                         'EmailAddress',
                         'BusinessPhone',
                         'MobilePhone'],
             'transitions': [{'id':'empty'}, ], # none
             'custom_actions':[{'id': 'save', 'title': 'Save'}, ]
             }
        ]

    def folderitems(self, full_objects = False):
        old_items = BikaListingView.folderitems(self)
        items = []
        for item in old_items:
            if not item.has_key('obj'):
                items.append(item)
                continue
            obj = item['obj']
            if obj.UID() in self.request.get('hide_uids', ()):
                continue
            item['Fullname'] = obj.getFullname()
            item['EmailAddress'] = obj.getEmailAddress()
            item['BusinessPhone'] = obj.getBusinessPhone()
            item['MobilePhone'] = obj.getMobilePhone()
            if self.request.get('selected_uids', '').find(item['uid']) > -1:
                item['selected'] = True
            items.append(item)
        return items

class AnalysisRequestSelectSampleView(BikaListingView):

    template = ViewPageTemplateFile("templates/analysisrequest_select_sample.pt")

    def __init__(self, context, request):
        super(AnalysisRequestSelectSampleView, self).__init__(context, request)
        self.icon = "++resource++bika.lims.images/sample_big.png"
        self.title = _("Select Sample")
        self.description = _("Click on a sample to create a secondary AR")
        c = context.portal_type == 'AnalysisRequest' and context.aq_parent or context
        self.contentFilter = {'portal_type': 'Sample',
                              'sort_on':'id',
                              'sort_order': 'reverse',
                              'review_state': ['to_be_sampled', 'to_be_preserved',
                                               'sample_due', 'sample_received'],
                              'cancellation_state': 'active',
                              'path': {"query": "/".join(c.getPhysicalPath()),
                                       "level" : 0 }
                              }
        self.show_sort_column = False
        self.show_select_row = False
        self.show_select_column = False
        self.show_workflow_action_buttons = False

        self.pagesize = 25

        request.set('disable_border', 1)

        self.columns = {
            'SampleID': {'title': _('Sample ID'),
                         'index': 'getSampleID', },
            'ClientSampleID': {'title': _('Client SID'),
                               'index': 'getClientSampleID', },
            'ClientReference': {'title': _('Client Reference'),
                                'index': 'getClientReference', },
            'SampleTypeTitle': {'title': _('Sample Type'),
                                'index': 'getSampleTypeTitle', },
            'SamplePointTitle': {'title': _('Sample Point'),
                                 'index': 'getSamplePointTitle', },
            'DateReceived': {'title': _('Date Received'),
                             'index': 'getDateReceived', },
            'SamplingDate': {'title': _('Sampling Date')},
            'state_title': {'title': _('State'),
                            'index': 'review_state', },
        }

        self.review_states = [
            {'id':'all',
             'title': _('All Samples'),
             'columns': ['SampleID',
                         'ClientReference',
                         'ClientSampleID',
                         'SampleTypeTitle',
                         'SamplePointTitle',
                         'SamplingDate',
                         'state_title']},
            {'id':'due',
             'title': _('Sample Due'),
             'contentFilter': {'review_state': 'sample_due'},
             'columns': ['SampleID',
                         'ClientReference',
                         'ClientSampleID',
                         'SampleTypeTitle',
                         'SamplePointTitle',
                         'SamplingDate']},
            {'id':'sample_received',
             'title': _('Sample Received'),
             'contentFilter': {'review_state': 'sample_received'},
             'columns': ['SampleID',
                         'ClientReference',
                         'ClientSampleID',
                         'SampleTypeTitle',
                         'SamplePointTitle',
                         'SamplingDate',
                         'DateReceived']},
        ]

    def folderitems(self, full_objects = False):
        items = BikaListingView.folderitems(self)
        translate = self.context.translation_service.translate
        for x in range(len(items)):
            if not items[x].has_key('obj'): continue
            obj = items[x]['obj']
            items[x]['class']['SampleID'] = "select_sample"
            if items[x]['uid'] in self.request.get('hide_uids', ''): continue
            if items[x]['uid'] in self.request.get('selected_uids', ''):
                items[x]['selected'] = True
            items[x]['view_url'] = obj.absolute_url() + "/view"
            items[x]['ClientReference'] = obj.getClientReference()
            items[x]['ClientSampleID'] = obj.getClientSampleID()
            items[x]['SampleID'] = obj.getSampleID()
            if obj.getSampleType().getHazardous():
                items[x]['after']['SampleID'] = \
                     "<img src='++resource++bika.lims.images/hazardous.png' title='%s'>"%\
                     translate(_("Hazardous"))
            items[x]['SampleTypeTitle'] = obj.getSampleTypeTitle()
            items[x]['SamplePointTitle'] = obj.getSamplePointTitle()
            items[x]['row_data'] = json.dumps({
                'SampleID': items[x]['title'],
                'ClientReference': items[x]['ClientReference'],
                'Requests': ", ".join([o.Title() for o in obj.getAnalysisRequests()]),
                'ClientSampleID': items[x]['ClientSampleID'],
                'DateReceived': obj.getDateReceived() and \
                               TimeOrDate(self.context, obj.getDateReceived()) or '',
                'SamplingDate': obj.getSamplingDate() and \
                               TimeOrDate(self.context, obj.getSamplingDate()) or '',
                'SampleType': items[x]['SampleTypeTitle'],
                'SamplePoint': items[x]['SamplePointTitle'],
                'Composite': obj.getComposite(),
                'field_analyses': self.FieldAnalyses(obj),
                'column': self.request.get('column', None),
            })
            items[x]['DateReceived'] = obj.getDateReceived() and \
                 TimeOrDate(self.context, obj.getDateReceived()) or ''
            items[x]['SamplingDate'] = obj.getSamplingDate() and \
                 TimeOrDate(self.context, obj.getSamplingDate()) or ''
        return items

    def FieldAnalyses(self, sample):
        """ Returns a dictionary of lists reflecting Field Analyses
            linked to this sample (meaning field analyses on this sample's
            first AR. For secondary ARs field analyses and their values are
            read/written from the first AR.)
            {category_uid: [service_uid, service_uid], ... }
        """
        res = {}
        ars = sample.getAnalysisRequests()
        if len(ars) > 0:
            for analysis in ars[0].getAnalyses(full_objects = True):
                service = analysis.getService()
                if service.getPointOfCapture() == 'field':
                    catuid = service.getCategoryUID()
                    if res.has_key(catuid):
                        res[catuid].append(service.UID())
                    else:
                        res[catuid] = [service.UID()]
        return res

class ajaxExpandCategory(BikaListingView):
    """ ajax requests pull this view for insertion when category header
    rows are clicked/expanded. """
    template = ViewPageTemplateFile("templates/analysisrequest_analysisservices.pt")

    def __call__(self):
        plone.protect.CheckAuthenticator(self.request.form)
        plone.protect.PostOnly(self.request.form)
        if hasattr(self.context, 'getRequestID'): self.came_from = "edit"
        return self.template()

    def Services(self, poc, CategoryUID):
        """ return a list of services brains """
        bsc = getToolByName(self.context, 'bika_setup_catalog')
        services = bsc(portal_type = "AnalysisService",
                       sort_on = 'sortable_title',
                       inactive_state = 'active',
                       getPointOfCapture = poc,
                       getCategoryUID = CategoryUID)
        return services


class ar_formdata(BrowserView):
    """Returns a JSON dictionary containing all the things the AR edit
    form might need.  This is just slightly better than encoding them
    in big comma-separated values in hidden form fields.  Lots of AJAX
    is not the answer though - the form needs to be quite responsive.
    """
    def __call__(self):
        plone.protect.CheckAuthenticator(self.request)
        translate = self.context.translate
        bsc = getToolByName(self.context, 'bika_setup_catalog')
        rc = getToolByName(self.context, REFERENCE_CATALOG)

        formdata = {
            'profiles':{},    # AR profiles
            'templates':{},   # AR templates
            'contact_ccs':{}, # default cc selections for all client contacts
            'categories':{},  # all services keyed by POC and category
            'services':{},    # info from all services, keyed by service uid
            'field_analyses':[], # list of field analysis UIDs
        }

        ## List of selected services for each ARProfile
        ## We store Title=Title and key=poc_categoryUID, val=[uid, uid, uid] in
        ## data[profiles][profileUID][services] for all services in each profile
        for context in (self.context, self.context.bika_setup.bika_arprofiles):
            profiles = [p for p in context.objectValues("ARProfile")
                        if isActive(p)]
            for profile in profiles:
                services = {}
                for service \
                    in bsc(portal_type = "AnalysisService",
                           inactive_state = "active",
                           UID = [u.UID() for u in profile.getService()]):
                    catUID = service.getCategoryUID
                    poc = service.getPointOfCapture
                    key = "%s_%s" % (poc, catUID)
                    try:
                        services[key].append(service.UID)
                    except:
                        services[key] = [service.UID, ]

                title = context == self.context.bika_setup.bika_arprofiles \
                    and translate(_('Lab')) + ": " + profile.Title() \
                    or profile.Title()

                p_dict = {
                    'UID':profile.UID(),
                    'Title':title,
                    'Services':services,
                }
                formdata['profiles'][profile.UID()] = p_dict

        ## parameters for all ARTemplates
        for context in (self.context, self.context.bika_setup.bika_arprofiles):
            templates = [t for t in context.objectValues("ARTemplate")
                         if isActive(t)]
            for template in templates:
                title = context == self.context.bika_setup.bika_arprofiles \
                    and translate(_('Lab')) + ": " + template.Title() \
                    or template.Title()
                sp_title = template.getSamplePoint()
                st_title = template.getSampleType()
                profile = template.getARProfile()
                t_dict = {
                    'UID':template.UID(),
                    'Title':template.Title(),
                    'ARProfile':profile and profile.UID() or '',
                    'SamplePoint':sp_title,
                    'SampleType':st_title,
                    'ReportDryMatter':template.getReportDryMatter(),
                }
                formdata['templates'][template.UID()] = t_dict

        # Store the default CCs for each client contact in form data.
        for contact in self.context.objectValues("Contact"):
            cc_uids = []
            cc_titles = []
            for cc in contact.getCCContact():
                cc_uids.append(cc.UID())
                cc_titles.append(cc.Title())
            c_dict = {
                'UID':contact.UID(),
                'Title':contact.Title(),
                'cc_uids':','.join(cc_uids),
                'cc_titles':','.join(cc_titles),
            }
            formdata['contact_ccs'][contact.UID()] = c_dict

        uc = getToolByName(self.context, 'uid_catalog')

        ## Loop ALL SERVICES
        for service in bsc(portal_type = "AnalysisService",
                           inactive_state = "active"):
            service = service.getObject()
            uid = service.UID()

            # Store categories: formdata['categories'][poc_catUID]: [uid, uid]
            catUID = service.getCategoryUID()
            poc = service.getPointOfCapture()
            key = "%s_%s" % (poc, catUID)
            try:
                formdata['categories'][key].append(uid)
            except:
                formdata['categories'][key] = [uid, ]

            # store field analyses so that the JS knows not to assign
            # partitions to these.
            poc = service.getPointOfCapture()
            if poc == 'field':
                formdata['field_analyses'].append(uid)

            ## Get dependants
            ## (this service's Calculation backrefs' dependencies)
            backrefs = []
            # this function follows all backreferences so we need skip to
            # avoid recursion. It should maybe be modified to be more smart...
            skip = []

            def walk(items):
                for item in items:
                    if item.portal_type == 'AnalysisService'\
                       and item.UID() != service.UID():
                        backrefs.append(item)
                    if item not in skip:
                        skip.append(item)
                        walk(item.getBackReferences())
            walk([service, ])

            ## Get dependencies
            ## (services we depend on)
            deps = {}
            calc = service.getCalculation()
            if calc:
                deps = calc.getCalculationDependencies()
                def walk(deps):
                    for service_uid, service_deps in deps.items():
                        if service_uid == uid:
                            # We can't be our own dep.
                            continue
                        service = rc.lookupObject(service_uid)
                        category = service.getCategory()
                        cat = '%s_%s' % (category.UID(), category.Title())
                        poc = '%s_%s' % (service.getPointOfCapture(), POINTS_OF_CAPTURE.getValue(service.getPointOfCapture()))
                        srv = '%s_%s' % (service.UID(), service.Title())
                        if not deps.has_key(poc): deps[poc] = {}
                        if not deps[poc].has_key(cat): deps[poc][cat] = []
                        deps[poc][cat].append(srv)
                        if service_deps:
                            walk(service_deps)
                walk(deps)

            # Get partition setup records for this service
            separate = service.getSeparate()
            containers = service.getContainer()
            preservations = service.getPreservation()
            partsetup = service.getPartitionSetup()

            # Single values become lists here
            for x in range(len(partsetup)):
                if partsetup[x].has_key('container') \
                   and type(partsetup[x]['container']) == str:
                    partsetup[x]['container'] = [partsetup[x]['container'],]
                if partsetup[x].has_key('preservation') \
                   and type(partsetup[x]['preservation']) == str:
                    partsetup[x]['preservation'] = [partsetup[x]['preservation'],]

            # If no dependents, backrefs or partition setup exists
            # nothing is stored for this service
            if not (backrefs or deps or separate or
                    containers or preservations or partsetup):
                continue

            # store info for this service
            formdata['services'][uid] = {
                'backrefs':[s.UID() for s in backrefs],
                'deps':deps,
            }

            formdata['services'][uid]['Separate'] = separate
            formdata['services'][uid]['Container'] = \
                [container.UID() for container in containers]
            formdata['services'][uid]['Preservation'] = \
                [pres.UID() for pres in preservations]
            formdata['services'][uid]['PartitionSetup'] = \
                partsetup

        ## SamplePoint and SampleType autocomplete lookups need a reference
        ## to resolve Title->UID
        formdata['st_uids'] = {}
        for s in bsc(portal_type = 'SampleType',
                        inactive_review_state = 'active'):
            s = s.getObject()
            formdata['st_uids'][s.Title()] = {
                'uid':s.UID(),
            }

        formdata['sp_uids'] = {}
        for s in bsc(portal_type = 'SamplePoint',
                        inactive_review_state = 'active'):
            s = s.getObject()
            formdata['sp_uids'][s.Title()] = {
                'uid':s.UID(),
                'composite':s.getComposite(),
            }

        return json.dumps(formdata)

class ajaxAnalysisRequestSubmit():

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def __call__(self):
        form = self.request.form
        plone.protect.CheckAuthenticator(self.request.form)
        plone.protect.PostOnly(self.request.form)
        translate = self.context.translation_service.translate
        came_from = form.has_key('came_from') and form['came_from'] or 'add'
        wftool = getToolByName(self.context, 'portal_workflow')
        pc = getToolByName(self.context, 'portal_catalog')
        bsc = getToolByName(self.context, 'bika_setup_catalog')

        SamplingWorkflowEnabled = self.context.bika_setup.getSamplingWorkflowEnabled()

        errors = {}
        def error(field = None, column = None, message = None):
            if not message:
                message = translate(PMF('Input is required but no input given.'))
            if (column or field):
                error_key = " %s.%s" % (int(column) + 1, field or '')
            else:
                error_key = "Form Error"
            errors[error_key] = message

        form_parts = json.loads(self.request.form['parts'])

        # First make a list of non-empty columns
        columns = []
        for column in range(int(form['col_count'])):
            formkey = "ar.%s" % column
            # first time in, unused columns not in form
            if not form.has_key(formkey):
                continue
            ar = form[formkey]
            if len(ar.keys()) == 3: # three empty price fields
                if ar.has_key('subtotal'):
                    continue
            columns.append(column)

        if len(columns) == 0:
            error(message = translate(_("No data was entered")))
            return json.dumps({'errors':errors})

        # Now some basic validation
        required_fields = ['SampleType', 'SamplingDate']
        validated_fields = ('SampleID', 'SampleType', 'SamplePoint')

        for column in columns:
            formkey = "ar.%s" % column
            ar = form[formkey]
            if not ar.has_key("Analyses"):
                error('Analyses', column, translate(_("No analyses have been selected")))

            # check that required fields have values
            for field in required_fields:
                if not ar.has_key(field):
                    error(field, column)

            # If a new ARTemplate or ARProfile's name is specified,
            # make sure it's clean.
            if ar.has_key('profileTitle'):
                if re.findall(r"[^A-Za-z\w\d\_\s]", ar['profileTitle']):
                    error(message="Validation failed: Profile title contains invalid characters")

            # validate field values
            for field in validated_fields:
                # ignore empty field values
                if not ar.has_key(field):
                    continue

                if field == "SampleID":
                    valid = True
                    try:
                        if not pc(portal_type = 'Sample',
                                  cancellation_state = 'active',
                                  id = ar[field]):
                            valid = False
                    except:
                        valid = False
                    if not valid:
                        msg = _("${id} is not a valid sample ID",
                                mapping={'id':ar[field]})
                        error(field, column, translate(msg))

                elif field == "SampleType":
                    valid = True
                    try:
                        if not bsc(portal_type = 'SampleType',
                                   inactive_state = 'active',
                                   Title = ar[field]):
                            valid = False
                    except:
                        valid = False
                    if not valid:
                        msg = _("${sampletype} is not a valid sample type",
                                mapping={'sampletype':ar[field]})
                        error(field, column, translate(msg))

                elif field == "SamplePoint":
                    valid = True
                    try:
                        if not bsc(portal_type = 'SamplePoint',
                                   inactive_state = 'active',
                                   Title = ar[field]):
                            valid = False
                    except:
                        valid = False
                    if not valid:
                        msg = _("${samplepoint} is not a valid sample point",
                                mapping={'samplepoint':ar[field]})
                        error(field, column, translate(msg))

        if errors:
            return json.dumps({'errors':errors})

        prices = form['Prices']
        ARs = []

        # if a new profile is created automatically,
        # this flag triggers the status message
        new_profile = None

        # The actual submission
        for column in columns:
            if form_parts:
                parts = form_parts[column]
            else:
                parts = []
            formkey = "ar.%s" % column
            values = form[formkey].copy()
            profile = None
            if (values.has_key('ARProfile')):
                profileUID = values['ARProfile']
                for proxy in bsc(portal_type = 'ARProfile',
                                 inactive_state = 'active',
                                 UID = profileUID):
                    profile = proxy.getObject()
            template = None
            if (values.has_key('ARTemplate')):
                templateUID = values['ARTemplate']
                for proxy in bsc(portal_type = 'ARTemplate',
                                 inactive_state = 'active',
                                 UID = templateUID):
                    template = proxy.getObject()

            if values.has_key('SampleID'):
                # Secondary AR
                sample_id = values['SampleID']
                sample_proxy = pc(portal_type = 'Sample',
                                  cancellation_state = 'active',
                                  id = sample_id)
                assert len(sample_proxy) == 1
                sample = sample_proxy[0].getObject()
                composite = values.get('Composite', False)
                sample.edit(Composite = composite)
                sample.reindexObject()
            else:
                # Primary AR
                client = self.context
                _id = client.invokeFactory('Sample', id = 'tmp')
                sample = client[_id]
                sample.edit(
                    ClientReference = values.get('ClientReference', ''),
                    ClientSampleID = values.get('ClientSampleID', ''),
                    SamplePoint = values.get('SamplePoint', ''),
                    SampleType = values['SampleType'],
                    SamplingDate = values['SamplingDate'],
                    Composite = values.get('Composite',False),
                    SamplingWorkflowEnabled = SamplingWorkflowEnabled,
                )
                sample.processForm()

                # Object has been renamed
                sample_id = sample.getId()
                sample.edit(SampleID = sample_id)

            sample_uid = sample.UID()

            if not parts:
                parts = [{'services':[],
                         'container':[],
                         'preservation':'',
                         'separate':False}]

            # Create sample partitions
            parts_and_services = {}
            for p in parts:
                _id = sample.invokeFactory('SamplePartition', id = 'tmp')
                part = sample[_id]
                container = p['container'] \
                    and type(p['container']) in (tuple, list) \
                    and p['container'][0] or p['container']
                part.edit(
                    Container = container,
                    Preservation = p['preservation'],
                )
                part.processForm()
                parts_and_services[part.id] = p['services']

            # create the AR

            Analyses = values['Analyses']
            del values['Analyses']

            _id = self.context.generateUniqueId('AnalysisRequest')
            self.context.invokeFactory('AnalysisRequest', id = _id)
            ar = self.context[_id]
            # ar.edit() for some fields before firing the event
            ar.edit(
                Contact = form['Contact'],
                CCContact = form['cc_uids'].split(","),
                CCEmails = form['CCEmails'],
                Sample = sample_uid,
                Profile = profile,
                **dict(values)
            )
            ar.processForm()
            # Object has been renamed
            ar_id = ar.getId()
            ar.edit(RequestID = ar_id)

            ARs.append(ar_id)

            new_analyses = ar.setAnalyses(Analyses, prices = prices)
            ar_analyses = ar.objectValues('Analysis')

            # Add analyses to sample partitions
            for part in sample.objectValues("SamplePartition"):
                part_services = parts_and_services[part.id]
                analyses = [a for a in new_analyses
                            if a.getServiceUID() in part_services]
                if analyses:
                    part.edit(
                        Analyses = analyses,
                    )
                    for analysis in analyses:
                        analysis.setSamplePartition(part)

            # If Preservation is required for some partitions,
            # and the SamplingWorkflow is disabled, we need
            # to transition to to_be_preserved manually.
            if not SamplingWorkflowEnabled:
                to_be_preserved = []
                sample_due = []
                lowest_state = 'sample_due'
                for p in sample.objectValues('SamplePartition'):
                    if p.getPreservation():
                        lowest_state = 'to_be_preserved'
                        to_be_preserved.append(p)
                    else:
                        sample_due.append(p)
                for p in to_be_preserved:
                    doActionFor(p, 'to_be_preserved')
                for p in sample_due:
                    doActionFor(p, 'sample_due')
                doActionFor(sample, lowest_state)
                doActionFor(ar, lowest_state)

            # Save new ARProfile/ARTemplate
            profile = None
            template = None
            if (values.has_key('profileTitle')):
                if self.request.ARProfileType == 'ARProfile':
                    # Save a normal AR Profile
                    _id = self.context.invokeFactory(type_name='ARProfile',
                                                     id='tmp')
                    profile = self.context[_id]
                    profile.edit(title = values['profileTitle'],
                                 Service = Analyses)
                    profile.processForm()
                    ar.edit(Profile = profile,
                            Template = None)
                else:
                    # saving a new AR Template

                    # First create new ARProfile if none was specified.
                    selected_arprofile = values.get('ARProfile', '')
                    if not selected_arprofile:
                        _id = self.context.invokeFactory(type_name='ARProfile',
                                                         id='tmp')
                        new_profile = self.context[_id]
                        message = translate(_("The AR Profile '${profile_name}' was "
                                              "automatically created.",
                                              mapping = {'profile_name':
                                                         values['profileTitle']}))
                        new_profile.edit(
                            title = values['profileTitle'],
                            description = message,
                            Service = Analyses)
                        new_profile.processForm()
                        selected_arprofile = new_profile

                    _id = self.context.invokeFactory(type_name='ARTemplate',
                                                     id='tmp')
                    template = self.context[_id]
                    template.edit(
                        title = values['profileTitle'],
                        ReportDryMatter = values.get('reportDryMatter', False),
                        SampleType = values.get('SampleType', ''),
                        SamplePoint = values.get('SamplePoint', ''),
                        ARProfile = selected_arprofile,
                    )
                    template.processForm()
                    ar.edit(Profile = selected_arprofile,
                            Template = template)

            if values.has_key('SampleID') and \
               wftool.getInfoFor(sample, 'review_state') != 'sample_due':
                wftool.doActionFor(ar, 'receive')

        if len(ARs) > 1:
            message = translate(_("Analysis requests ${ARs} were "
                                  "successfully created.",
                                  mapping = {'ARs': ', '.join(ARs)}))
        else:
            message = translate(_("Analysis request ${AR} was "
                                  "successfully created.",
                                  mapping = {'AR': ARs[0]}))

        self.context.plone_utils.addPortalMessage(message, 'info')

        if new_profile:
            message = translate(_("The AR Profile '${profile_name}' was "
                                  "automatically created.",
                                  mapping = {'profile_name': new_profile.Title()}))
            self.context.plone_utils.addPortalMessage(message, 'info')

        # automatic label printing
        # won't print labels for Register on Secondary ARs
        new_ars = None
        if came_from == 'add':
            new_ars = [ar for ar in ARs if ar.split("-")[-1] == '01']
        if 'register' in self.context.bika_setup.getAutoPrintLabels() and new_ars:
            return json.dumps({'success':message,
                               'labels':new_ars,
                               'labelsize':self.context.bika_setup.getAutoLabelSize()})
        else:
            return json.dumps({'success':message})

class AnalysisRequestsView(BikaListingView):
    implements(IViewView)

    def __init__(self, context, request):
        super(AnalysisRequestsView, self).__init__(context, request)

        self.contentFilter = {'portal_type':'AnalysisRequest',
                              'sort_on':'id',
                              'sort_order': 'reverse',
                              'path': {"query": "/", "level" : 0 }
                              }

        self.review_state = 'all'

        self.context_actions = {}

        if self.context.portal_type == "Client":
            if self.view_url.find("analysisrequests") == -1:
                self.view_url = self.view_url + "/analysisrequests"
        else:
            self.request.set('disable_border', 1)

        translate = self.context.translation_service.translate

        self.allow_edit = True

        self.show_sort_column = False
        self.show_select_row = False
        self.show_select_column = True

        self.icon = "++resource++bika.lims.images/analysisrequest_big.png"
        self.title = _("Analysis Requests")
        self.description = ""

        SamplingWorkflowEnabled = self.context.bika_setup.getSamplingWorkflowEnabled()

        mtool = getToolByName(self.context, 'portal_membership')
        member = mtool.getAuthenticatedMember()
        user_is_preserver = 'Preserver' in member.getRoles()

        self.columns = {
            'getRequestID': {'title': _('Request ID'),
                             'index': 'getRequestID'},
            'getClientOrderNumber': {'title': _('Client Order'),
                                     'index': 'getClientOrderNumber',
                                     'toggle': False},
            'Creator': {'title': PMF('Creator'),
                                     'index': 'Creator',
                                     'toggle': False},
            'Created': {'title': PMF('Date Created'),
                                     'toggle': False},
            'getSample': {'title': _("Sample"),
                          'toggle': False,},
            'Client': {'title': _('Client'),
                       'toggle': True},
            'getClientReference': {'title': _('Client Ref'),
                                   'index': 'getClientReference',
                                   'toggle': False},
            'getClientSampleID': {'title': _('Client SID'),
                                  'index': 'getClientSampleID',
                                  'toggle': False},
            'getSampleTypeTitle': {'title': _('Sample Type'),
                                   'index': 'getSampleTypeTitle',
                                   'toggle': True},
            'getSamplePointTitle': {'title': _('Sample Point'),
                                    'index': 'getSamplePointTitle',
                                    'toggle': False},
            'SamplingDate': {'title': _('Sampling Date'),
                             'toggle': True},
            'getDateSampled': {'title': _('Date Sampled'),
                               'toggle': not SamplingWorkflowEnabled,
                               'input_class': 'datepicker_nofuture',
                               'input_width': '10'},
            'getSampler': {'title': _('Sampler'),
                           'toggle': not SamplingWorkflowEnabled},
            'getDatePreserved': {'title': _('Date Preserved'),
                                 'toggle': user_is_preserver,
                                 'input_class': 'datepicker_nofuture',
                                 'input_width': '10'},
            'getPreserver': {'title': _('Preserver'),
                             'toggle': user_is_preserver},
            'getDatePreserved': {'title': _('Date Preserved'),
                               'input_class': 'datepicker_nofuture',
                               'input_width': '10'},
            'getPreserver': {'title': _('Preserver')},
            'getDateReceived': {'title': _('Date Received'),
                                'index': 'getDateReceived',
                                'toggle': False},
            'getDatePublished': {'title': _('Date Published'),
                                 'index': 'getDatePublished',
                                 'toggle': False},
            'state_title': {'title': _('State'),
                            'index': 'review_state'},
        }
        self.review_states = [
            {'id':'all',
             'title': _('All'),
             'transitions': [{'id':'sampled'},
                             {'id':'preserved'},
                             {'id':'receive'},
                             {'id':'retract'},
                             {'id':'verify'},
                             {'id':'prepublish'},
                             {'id':'publish'},
                             {'id':'republish'},
                             {'id':'cancel'},
                             {'id':'reinstate'}],
             'columns':['getRequestID',
                        'getSample',
                        'Client',
                        'Creator',
                        'Created',
                        'getClientOrderNumber',
                        'getClientReference',
                        'getClientSampleID',
                        'getSampleTypeTitle',
                        'getSamplePointTitle',
                        'SamplingDate',
                        'getDateSampled',
                        'getSampler',
                        'getDatePreserved',
                        'getPreserver',
                        'getDateReceived',
                        'state_title']},
            {'id':'sample_due',
             'title': _('Due'),
             'contentFilter': {'review_state': ('to_be_sampled',
                                                'to_be_preserved',
                                                'sample_due'),
                               'sort_on':'id',
                               'sort_order': 'reverse'},
             'transitions': [{'id':'sampled'},
                             {'id':'preserved'},
                             {'id':'receive'},
                             {'id':'cancel'},
                             {'id':'reinstate'}],
             'columns':['getRequestID',
                        'getSample',
                        'Client',
                        'Creator',
                        'Created',
                        'getClientOrderNumber',
                        'getClientReference',
                        'getClientSampleID',
                        'getDateSampled',
                        'getSampler',
                        'getDatePreserved',
                        'getPreserver',
                        'getSampleTypeTitle',
                        'getSamplePointTitle',
                        'state_title']},
           {'id':'sample_received',
             'title': _('Received'),
             'contentFilter': {'review_state': 'sample_received',
                               'sort_on':'id',
                               'sort_order': 'reverse'},
             'transitions': [{'id':'prepublish'},
                             {'id':'cancel'},
                             {'id':'reinstate'}],
             'columns':['getRequestID',
                        'getSample',
                        'Client',
                        'Creator',
                        'Created',
                        'getClientOrderNumber',
                        'getClientReference',
                        'getClientSampleID',
                        'getSampleTypeTitle',
                        'getSamplePointTitle',
                        'getDateSampled',
                        'getSampler',
                        'getDatePreserved',
                        'getPreserver',
                        'getDateReceived']},
            {'id':'to_be_verified',
             'title': _('To be verified'),
             'contentFilter': {'review_state': 'to_be_verified',
                               'sort_on':'id',
                               'sort_order': 'reverse'},
             'transitions': [{'id':'retract'},
                             {'id':'verify'},
                             {'id':'prepublish'},
                             {'id':'cancel'},
                             {'id':'reinstate'}],
             'columns':['getRequestID',
                        'getSample',
                        'Client',
                        'Creator',
                        'Created',
                        'getClientOrderNumber',
                        'getClientReference',
                        'getClientSampleID',
                        'getSampleTypeTitle',
                        'getSamplePointTitle',
                        'getDateSampled',
                        'getSampler',
                        'getDatePreserved',
                        'getPreserver',
                        'getDateReceived']},
            {'id':'verified',
             'title': _('Verified'),
             'contentFilter': {'review_state': 'verified',
                               'sort_on':'id',
                               'sort_order': 'reverse'},
             'transitions': [{'id':'publish'}],
             'columns':['getRequestID',
                        'getSample',
                        'Client',
                        'Creator',
                        'Created',
                        'getClientOrderNumber',
                        'getClientReference',
                        'getClientSampleID',
                        'getSampleTypeTitle',
                        'getSamplePointTitle',
                        'getDateSampled',
                        'getSampler',
                        'getDatePreserved',
                        'getPreserver',
                        'getDateReceived']},
            {'id':'published',
             'title': _('Published'),
             'contentFilter': {'review_state': 'published',
                               'sort_on':'id',
                               'sort_order': 'reverse'},
             'columns':['getRequestID',
                        'getSample',
                        'Client',
                        'Creator',
                        'Created',
                        'getClientOrderNumber',
                        'getClientReference',
                        'getClientSampleID',
                        'getSampleTypeTitle',
                        'getSamplePointTitle',
                        'getDateSampled',
                        'getSampler',
                        'getDatePreserved',
                        'getPreserver',
                        'getDateReceived',
                        'getDatePublished']},
            {'id':'cancelled',
             'title': _('Cancelled'),
             'contentFilter': {'cancellation_state': 'cancelled',
                               'review_state': ('to_be_sampled', 'to_be_preserved',
                                                'sample_due', 'sample_received',
                                                'to_be_verified', 'attachment_due',
                                                'verified', 'published'),
                               'sort_on':'id',
                               'sort_order': 'reverse'},
             'transitions': [{'id':'reinstate'}],
             'columns':['getRequestID',
                        'getSample',
                        'Client',
                        'Creator',
                        'Created',
                        'getClientOrderNumber',
                        'getClientReference',
                        'getClientSampleID',
                        'getSampleTypeTitle',
                        'getSamplePointTitle',
                        'getDateSampled',
                        'getSampler',
                        'getDatePreserved',
                        'getPreserver',
                        'getDateReceived',
                        'getDatePublished',
                        'state_title']},
            {'id':'assigned',
             'title': "<img title='%s' src='++resource++bika.lims.images/assigned.png'/>" %
                        translate(_("Assigned")),
             'contentFilter': {'worksheetanalysis_review_state': 'assigned',
                               'review_state': ('sample_received', 'to_be_verified',
                                                'attachment_due', 'verified',
                                                'published'),
                               'sort_on':'id',
                               'sort_order': 'reverse'},
             'transitions': [{'id':'retract'},
                             {'id':'verify'},
                             {'id':'prepublish'},
                             {'id':'publish'},
                             {'id':'republish'},
                             {'id':'cancel'},
                             {'id':'reinstate'}],
             'columns':['getRequestID',
                        'getSample',
                        'Client',
                        'Creator',
                        'Created',
                        'getClientOrderNumber',
                        'getClientReference',
                        'getClientSampleID',
                        'getSampleTypeTitle',
                        'getSamplePointTitle',
                        'getDateSampled',
                        'getSampler',
                        'getDatePreserved',
                        'getPreserver',
                        'getDateReceived',
                        'state_title']},
            {'id':'unassigned',
             'title': "<img title='%s' src='++resource++bika.lims.images/unassigned.png'/>" %
                        translate(_("Unassigned")),
             'contentFilter': {'worksheetanalysis_review_state': 'unassigned',
                               'review_state': ('sample_received', 'to_be_verified',
                                                'attachment_due', 'verified',
                                                'published'),
                               'sort_on':'id',
                               'sort_order': 'reverse'},
             'transitions': [{'id':'receive'},
                             {'id':'retract'},
                             {'id':'verify'},
                             {'id':'prepublish'},
                             {'id':'publish'},
                             {'id':'republish'},
                             {'id':'cancel'},
                             {'id':'reinstate'}],
             'columns':['getRequestID',
                        'getSample',
                        'Client',
                        'Creator',
                        'Created',
                        'getClientOrderNumber',
                        'getClientReference',
                        'getClientSampleID',
                        'getSampleTypeTitle',
                        'getSamplePointTitle',
                        'SamplingDate',
                        'getDateSampled',
                        'getSampler',
                        'getDatePreserved',
                        'getPreserver',
                        'getDateReceived',
                        'state_title']},
            ]

    def folderitems(self, full_objects = False):
        workflow = getToolByName(self.context, "portal_workflow")
        items = BikaListingView.folderitems(self)
        mtool = getToolByName(self.context, 'portal_membership')
        member = mtool.getAuthenticatedMember()
        translate = self.context.translation_service.translate

        for x in range(len(items)):
            if not items[x].has_key('obj'): continue
            obj = items[x]['obj']
            sample = obj.getSample()

            if getSecurityManager().checkPermission(EditResults, obj):
                url = obj.absolute_url() + "/manage_results"
            else:
                url = obj.absolute_url()

            items[x]['getRequestID'] = obj.getRequestID()
            items[x]['replace']['getRequestID'] = "<a href='%s'>%s</a>" % \
                 (url, items[x]['getRequestID'])

            items[x]['Client'] = obj.aq_parent.Title()
            items[x]['replace']['Client'] = "<a href='%s'>%s</a>" % \
                 (obj.aq_parent.absolute_url(), obj.aq_parent.Title())

            items[x]['Creator'] = pretty_user_name_or_id(self.context,
                                                         obj.Creator())

            samplingdate = obj.getSample().getSamplingDate()
            items[x]['SamplingDate'] = TimeOrDate(self.context, samplingdate, long_format = 0)

            items[x]['getDateReceived'] = TimeOrDate(self.context, obj.getDateReceived())
            items[x]['getDatePublished'] =  TimeOrDate(self.context, obj.getDatePublished())

            state = workflow.getInfoFor(obj, 'worksheetanalysis_review_state')
            if state == 'assigned':
                items[x]['after']['state_title'] = \
                    "<img src='++resource++bika.lims.images/worksheet.png' title='%s'/>" % \
                    translate(_("All analyses assigned"))

            after_icons = ""
            if obj.getLate():
                after_icons += "<img src='++resource++bika.lims.images/late.png' title='%s'>" % \
                    translate(_("Late Analyses"))
            if samplingdate > DateTime():
                after_icons += "<img src='++resource++bika.lims.images/calendar.png' title='%s'>" % \
                    translate(_("Future dated sample"))
            if obj.getInvoiceExclude():
                after_icons += "<img src='++resource++bika.lims.images/invoice_exclude.png' title='%s'>" % \
                    translate(_("Exclude from invoice"))
            if sample.getSampleType().getHazardous():
                after_icons += "<img src='++resource++bika.lims.images/hazardous.png' title='%s'>" % \
                    translate(_("Hazardous"))
            if after_icons:
                items[x]['after']['getRequestID'] = after_icons

            items[x]['Created'] = TimeOrDate(self.context,
                                             obj.created())

            items[x]['getSample'] = sample
            items[x]['replace']['getSample'] = \
                "<a href='%s'>%s</a>" % (sample.absolute_url(), sample.Title())

            if not samplingdate > DateTime():
                datesampled = TimeOrDate(self.context, sample.getDateSampled())
                if not datesampled:
                    datesampled = TimeOrDate(self.context, DateTime(),
                                             long_format=1, with_time = False)
                    items[x]['class']['getDateSampled'] = 'provisional'
                sampler = sample.getSampler().strip()
                if sampler:
                    items[x]['replace']['getSampler'] = pretty_user_name_or_id(
                        self.context, sampler)
                if 'Sampler' in member.getRoles() and not sampler:
                    sampler = member.id
                    items[x]['class']['getSampler'] = 'provisional'
            else:
                datesampled = ''
                sampler = ''
            items[x]['getDateSampled'] = datesampled
            items[x]['getSampler'] = sampler


            # sampling workflow - inline edits for Sampler and Date Sampled
            checkPermission = self.context.portal_membership.checkPermission
            if checkPermission(SampleSample, obj) \
                and not samplingdate > DateTime():
                items[x]['required'] = ['getSampler', 'getDateSampled']
                items[x]['allow_edit'] = ['getSampler', 'getDateSampled']
                samplers = getUsers(sample, ['Sampler', 'LabManager', 'Manager'])
                username = mtool.getAuthenticatedMember().getUserName()
                users = [({'ResultValue': u, 'ResultText': samplers.getValue(u)})
                         for u in samplers]
                items[x]['choices'] = {'getSampler': users}
                Sampler = sampler and sampler or \
                    (username in samplers.keys() and username) or ''
                items[x]['getSampler'] = Sampler

            # These don't exist on ARs
            # the columns exist just to set "preserved" from lists.
            # XXX This should be a list of preservers...
            items[x]['getPreserver'] = ''
            items[x]['getDatePreserved'] = ''

            # inline edits for Preserver and Date Preserved
            checkPermission = self.context.portal_membership.checkPermission
            if checkPermission(PreserveSample, obj):
                items[x]['required'] = ['getPreserver', 'getDatePreserved']
                items[x]['allow_edit'] = ['getPreserver', 'getDatePreserved']
                preservers = getUsers(obj, ['Preserver', 'LabManager', 'Manager'])
                username = mtool.getAuthenticatedMember().getUserName()
                users = [({'ResultValue': u, 'ResultText': preservers.getValue(u)})
                         for u in preservers]
                items[x]['choices'] = {'getPreserver': users}
                preserver = username in preservers.keys() and username or ''
                items[x]['getPreserver'] = preserver
                items[x]['getDatePreserved'] = TimeOrDate(
                    self.context, DateTime(), long_format=1, with_time=False)
                items[x]['class']['getPreserver'] = 'provisional'
                items[x]['class']['getDatePreserved'] = 'provisional'

        return items
