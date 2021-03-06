from AccessControl import ModuleSecurityInfo, allow_module
from DateTime import DateTime
from Products.Archetypes.public import DisplayList
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.TranslationServiceTool import TranslationServiceTool
from Products.Five.browser import BrowserView
from bika.lims import bikaMessageFactory as _
from bika.lims import interfaces
from bika.lims import logger
from bika.lims.config import POINTS_OF_CAPTURE
from bika.lims.config import Publish
from email.Utils import formataddr
from plone.i18n.normalizer.interfaces import IIDNormalizer
from reportlab.graphics.barcode import getCodes, getCodeNames, createBarcodeDrawing
from zope.component import getUtility
from zope.interface import providedBy
import copy,re,urllib
import json
import plone.protect
import transaction

ModuleSecurityInfo('email.Utils').declarePublic('formataddr')
allow_module('csv')

# Wrapper for PortalTransport's sendmail - don't know why there sendmail
# method is marked private
ModuleSecurityInfo('Products.bika.utils').declarePublic('sendmail')
#Protected( Publish, 'sendmail')
def sendmail(portal, from_addr, to_addrs, msg):
    mailspool = portal.portal_mailspool
    mailspool.sendmail(from_addr, to_addrs, msg)

ModuleSecurityInfo('Products.bika.utils').declarePublic('printfile')
def printfile(portal, from_addr, to_addrs, msg):
    import os

    """ set the path, then the cmd 'lpr filepath'
    temp_path = 'C:/Zope2/Products/Bika/version.txt'

    os.system('lpr "%s"' %temp_path)
    """
    pass

def getUsers(context, roles, allow_empty=True):
    """ Present a DisplayList containing users in the specified
        list of roles
    """
    mtool = getToolByName(context, 'portal_membership')
    pairs = allow_empty and [['','']] or []
    users = mtool.searchForMembers(roles = roles)
    for user in users:
        uid = user.getId()
        fullname = user.getProperty('fullname')
        if fullname is None:
            fullname = uid
        pairs.append((uid, fullname))
    pairs.sort(lambda x, y: cmp(x[1], y[1]))
    return DisplayList(pairs)

def isActive(obj):
    """ Check if obj is inactive or cancelled.
    """
    wf = getToolByName(obj, 'portal_workflow')
    if (hasattr(obj, 'inactive_state') and obj.inactive_state == 'inactive') or \
       wf.getInfoFor(obj, 'inactive_state', 'active') == 'inactive':
        return False
    if (hasattr(obj, 'cancellation_state') and obj.inactive_state == 'cancelled') or \
       wf.getInfoFor(obj, 'cancellation_state', 'active') == 'cancelled':
        return False
    return True

def formatDateQuery(context, date_id):
    """ Obtain and reformat the from and to dates
        into a date query construct
    """
    from_date = context.REQUEST.get('%s_fromdate' % date_id, None)
    if from_date:
        from_date = from_date + ' 00:00'
    to_date = context.REQUEST.get('%s_todate' % date_id, None)
    if to_date:
        to_date = to_date + ' 23:59'

    date_query = {}
    if from_date and to_date:
        date_query = {'query': [from_date, to_date],
                      'range': 'min:max'}
    elif from_date or to_date:
        date_query = {'query': from_date or to_date,
                      'range': from_date and 'min' or 'max'}

    return date_query

def formatDateParms(context, date_id):
    """ Obtain and reformat the from and to dates
        into a printable date parameter construct
    """
    from_date = context.REQUEST.get('%s_fromdate' % date_id, None)
    to_date = context.REQUEST.get('%s_todate' % date_id, None)

    date_parms = {}
    if from_date and to_date:
        date_parms = 'from %s to %s' %(from_date, to_date)
    elif from_date:
        date_parms = 'from %s' %(from_date)
    elif to_date:
        date_parms = 'to %s' %(to_date)

    return date_parms

def TimeOrDate(context, datetime, long_format = False, with_time = True):
    """ Return the Time date is today,
        otherwise return the Date.
    """
    localLongTimeFormat = context.portal_properties.site_properties.getProperty('localLongTimeFormat')
    localTimeFormat = context.portal_properties.site_properties.getProperty('localTimeFormat')
    localTimeOnlyFormat = context.portal_properties.site_properties.getProperty('localTimeOnlyFormat')

    if hasattr(datetime, 'Date'):
        if (datetime.Date() > DateTime().Date()) or long_format:
            if with_time:
                dt = datetime.asdatetime().strftime(localLongTimeFormat)
            else:
                dt = datetime.asdatetime().strftime(localTimeFormat)
        elif (datetime.Date() < DateTime().Date()):
            dt = datetime.asdatetime().strftime(localTimeFormat)
        elif datetime.Date() == DateTime().Date():
            dt = datetime.asdatetime().strftime(localTimeOnlyFormat)
        else:
            dt = datetime.asdatetime().strftime(localTimeFormat)
        dt = dt.replace("PM", "pm").replace("AM", "am")
        if len(dt) > 10:
            dt = dt.replace("12:00 am", "")
        if dt == "12:00 am":
            dt = datetime.asdatetime().strftime(localTimeFormat)
    else:
        dt = datetime
    return dt

# encode_header function copied from roundup's rfc2822 package.
hqre = re.compile(r'^[A-z0-9!"#$%%&\'()*+,-./:;<=>?@\[\]^_`{|}~ ]+$')

ModuleSecurityInfo('Products.bika.utils').declarePublic('encode_header')
def encode_header(header, charset = 'utf-8'):
    """ Will encode in quoted-printable encoding only if header
    contains non latin characters
    """

    # Return empty headers unchanged
    if not header:
        return header

    # return plain header if it does not contain non-ascii characters
    if hqre.match(header):
        return header

    quoted = ''
    #max_encoded = 76 - len(charset) - 7
    for c in header:
        # Space may be represented as _ instead of =20 for readability
        if c == ' ':
            quoted += '_'
        # These characters can be included verbatim
        elif hqre.match(c):
            quoted += c
        # Otherwise, replace with hex value like =E2
        else:
            quoted += "=%02X" % ord(c)
            plain = 0

    return '=?%s?q?%s?=' % (charset, quoted)

def zero_fill(matchobj):
    return matchobj.group().zfill(8)

num_sort_regex = re.compile('\d+')

ModuleSecurityInfo('Products.bika.utils').declarePublic('sortable_title')
def sortable_title(portal, title):
    """Convert title to sortable title
    """
    if not title:
        return ''

    def_charset = portal.plone_utils.getSiteEncoding()
    sortabletitle = title.lower().strip()
    # Replace numbers with zero filled numbers
    sortabletitle = num_sort_regex.sub(zero_fill, sortabletitle)
    # Truncate to prevent bloat
    for charset in [def_charset, 'latin-1', 'utf-8']:
        try:
            sortabletitle = unicode(sortabletitle, charset)[:30]
            sortabletitle = sortabletitle.encode(def_charset or 'utf-8')
            break
        except UnicodeError:
            pass
        except TypeError:
            # If we get a TypeError if we already have a unicode string
            sortabletitle = sortabletitle[:30]
            break
    return sortabletitle

def pretty_user_name_or_id(context, userid):
    pc = getToolByName(context, 'portal_catalog')
    r = pc(portal_type = 'Contact', getUsername = userid)
    if len(r) == 1:
        return r[0].Title

    mtool = getToolByName(context, 'portal_membership')
    member = mtool.getMemberById(userid)
    if member is None:
        return userid
    else:
        fullname = member.getProperty('fullname')
    if fullname in (None, ''):
        return userid
    return fullname

def pretty_user_email(context, userid):
    pc = getToolByName(context, 'portal_catalog')
    r = pc(portal_type = 'Contact', getUsername = userid)
    if len(r) == 1:
        contact = r[0].getObject()
        return contact.getEmailAddress()

    mtool = getToolByName(context, 'portal_membership')
    member = mtool.getMemberById(userid)
    if member is None:
        return None
    else:
        return member.getProperty('email')

def changeWorkflowState(content, state_id, acquire_permissions=False,
                        portal_workflow=None, **kw):
    """Change the workflow state of an object
    @param content: Content obj which state will be changed
    @param state_id: name of the state to put on content
    @param acquire_permissions: True->All permissions unchecked and on riles and
                                acquired
                                False->Applies new state security map
    @param portal_workflow: Provide workflow tool (optimisation) if known
    @param kw: change the values of same name of the state mapping
    @return: None
    """

    if portal_workflow is None:
        portal_workflow = getToolByName(content, 'portal_workflow')

    # Might raise IndexError if no workflow is associated to this type
    wf_def = portal_workflow.getWorkflowsFor(content)[0]
    wf_id= wf_def.getId()

    wf_state = {
        'action': None,
        'actor': None,
        'comments': "Setting state to %s" % state_id,
        'review_state': state_id,
        'time': DateTime(),
        }

    # Updating wf_state from keyword args
    for k in kw.keys():
        # Remove unknown items
        if not wf_state.has_key(k):
            del kw[k]
    if kw.has_key('review_state'):
        del kw['review_state']
    wf_state.update(kw)

    portal_workflow.setStatusOf(wf_id, content, wf_state)

    if acquire_permissions:
        # Acquire all permissions
        for permission in content.possible_permissions():
            content.manage_permission(permission, acquire=1)
    else:
        # Setting new state permissions
        wf_def.updateRoleMappingsFor(content)

    # Map changes to the catalogs
    content.reindexObject(idxs=['allowedRolesAndUsers', 'review_state'])
    return

class bsc_counter(BrowserView):
    def __call__(self):
        bsc = getToolByName(self.context, 'bika_setup_catalog')
        return bsc.getCounter()

class bsc_browserdata(BrowserView):
    """Returns information about services from bika_setup_catalog.
    This view is called from ./js/bika.js and it's output is cached
    in browser localStorage.
    """
    def __call__(self):
        translate = self.context.translate
        bsc = getToolByName(self.context, 'bika_setup_catalog')

        data = {
            'categories':{},  # services keyed by "POC_category"
            'services':{},    # service info, keyed by UID
        }

        ## Loop ALL SERVICES
        services = dict([(b.UID, b.getObject()) for b
                         in bsc(portal_type = "AnalysisService",
                                inactive_state = "active")])

        for uid, service in services.items():

            ## Store categories
            ## data['categories'][poc_catUID]: [uid, uid]
            key = "%s_%s" % (service.getPointOfCapture(),
                             service.getCategoryUID())
            if key in data['categories']:
                data['categories'][key].append(uid)
            else:
                data['categories'][key] = [uid, ]

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
                    for depserv_uid, depserv_deps in deps.items():
                        if depserv_uid == uid:
                            continue
                        depserv = services[depserv_uid]
                        category = depserv.getCategory()
                        cat = '%s_%s' % (category.UID(), category.Title())
                        poc = '%s_%s' % \
                            (depserv.getPointOfCapture(),
                             POINTS_OF_CAPTURE.getValue(depserv.getPointOfCapture()))
                        srv = '%s_%s' % (depserv.UID(), depserv.Title())
                        if not deps.has_key(poc): deps[poc] = {}
                        if not deps[poc].has_key(cat): deps[poc][cat] = []
                        deps[poc][cat].append(srv)
                        if depserv_deps:
                            walk(depserv_deps)
                walk(deps)

            ## Get partition setup records for this service
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

            ## If no dependents, backrefs or partition setup exists
            ## nothing is stored for this service
            if not (backrefs or deps or separate or
                    containers or preservations or partsetup):
                continue

            # store info for this service
            data['services'][uid] = {
                'backrefs':[s.UID() for s in backrefs],
                'deps':deps,
            }

            data['services'][uid]['Separate'] = separate
            data['services'][uid]['Container'] = \
                [container.UID() for container in containers]
            data['services'][uid]['Preservation'] = \
                [pres.UID() for pres in preservations]
            data['services'][uid]['PartitionSetup'] = \
                partsetup

        uc = getToolByName(self.context, 'uid_catalog')

        ## SamplePoint and SampleType autocomplete lookups need a reference
        ## to resolve Title->UID
        data['st_uids'] = {}
        for s in bsc(portal_type = 'SampleType',
                        inactive_review_state = 'active'):
            s = s.getObject()
            data['st_uids'][s.Title()] = {
                'uid':s.UID(),
            }

        data['sp_uids'] = {}
        for s in bsc(portal_type = 'SamplePoint',
                        inactive_review_state = 'active'):
            s = s.getObject()
            data['sp_uids'][s.Title()] = {
                'uid':s.UID(),
                'composite':s.getComposite(),
            }

        data['containers'] = {}
        for s in bsc(portal_type = 'Container'):
            s = s.getObject()
            data['containers'][s.UID()] = {
                'title':s.Title(),
            }

        data['preservations'] = {}
        for s in bsc(portal_type = 'Preservation'):
            s = s.getObject()
            data['preservations'][s.UID()] = {
                'title':s.Title(),
            }

        return json.dumps(data)
