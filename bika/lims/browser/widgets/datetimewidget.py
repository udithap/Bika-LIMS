from AccessControl import ClassSecurityInfo
from Products.Archetypes.Widget import TypesWidget
from Products.Archetypes.Registry import registerWidget
from bika.lims.utils import TimeOrDate

class DateTimeWidget(TypesWidget):
    _properties = TypesWidget._properties.copy()
    _properties.update({
        'TimeOrDate': TimeOrDate,
        'macro': "bika_widgets/datetimewidget",
        'helper_js': ("bika_widgets/datetimewidget.js",),
        'helper_css': ("bika_widgets/datetimewidget.css",),
    })

    security = ClassSecurityInfo()

registerWidget(DateTimeWidget,
               title = 'DateTimeWidget',
               description = ('Simple text field, with a jquery date widget attached.'),
               )
