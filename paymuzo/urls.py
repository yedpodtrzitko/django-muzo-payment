# paymuzo

from django.conf.urls.defaults import patterns

urlpatterns = patterns('paymuzo.views',
    (r'^pay_proform/(?P<proform_id>[0-9]+)/$', 'redirect_proform_to_muzo'),
    (r'^verify_proform/(?P<proform_id>[0-9]+)/$', 'catch_proform_muzo_response')
)
