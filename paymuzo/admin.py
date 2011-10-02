from django.contrib import admin
from models import MuzoConfiguration

class MuzoConfigurationAdmin(admin.ModelAdmin):

    list_display = ('merchant_number',)

    fields = ('gate_url', 'muzo_public_key', 'merchant_number', \
              'last_payment_attempt', 'merchant_private_key', 'payment_type')
    #readonly_fields = ('',)

admin.site.register(MuzoConfiguration, MuzoConfigurationAdmin)
