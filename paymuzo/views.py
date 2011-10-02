from django.core.urlresolvers import reverse
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import ugettext_lazy as _
from paymuzo.models import MuzoConfiguration

def redirect_proform_to_muzo(request, proform_id):
    """ presmerovani na MUZO terminal """
    mc = MuzoConfiguration.get_default()

    url = mc.gate_url + '?' + mc.get_url_params_string_by_proform(proform_id)
    print 'muzo redirect to url: %s' % url

    return HttpResponseRedirect(url)

def catch_proform_muzo_response(request, proform_id):
    """ osetreni navratu z MUZO """
    mc = MuzoConfiguration.get_default()

    proform = mc.get_proform_from_response(request, proform_id)
    ok = mc.verify_proform_payment(request, proform)

    if ok:
        return HttpResponseRedirect(reverse('payment_done', args=[int(proform.get_order().pk)]))
    else:
        messages.error(request, _("Muzo payment failed, try again"))
        return HttpResponseRedirect(reverse('invoice.views.change_proform_payment', args=[int(proform_id)]))
