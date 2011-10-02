from django.db import models
from django.utils.translation import ugettext as _
from django.contrib.sites.models import Site
from django.conf import settings
import M2Crypto, base64

class MuzoConfiguration(models.Model):
    '''
    # pripojeni na payment_type = 'muzo'
    #sifrovani pomoci sha1+RSA
    #delka klice 2048
    '''
    gate_url = models.CharField(_("Gate url"), max_length=256, blank=True)
    default_lang = models.CharField(_("Gate language"), max_length=4, blank=True, null=True)
    #overeni podpisu
    muzo_public_key = models.CharField(_("Muzo public key"), max_length=4096, blank=True)

    merchant_number = models.IntegerField(_("Merchant ID"), unique=True)

    # identifikace platby unikatni vuci zakaznikovi - order number
    last_payment_attempt = models.IntegerField(_("Last payment attempt"))

    #podepsani pozadavku
    merchant_private_key = models.CharField(_("Merchant private key"), max_length=4096, blank=True)
    merchant_public_key = models.CharField(_("Merchant public key"), max_length=4096, blank=True)

    # v pripade vicenasobneho vyuziti muza napr pro rozlozene platby
    payment_type = models.ForeignKey(PaymentType, verbose_name=_("Payment type"))
    agency = models.ForeignKey('participant.agency', null=True)

    _params_order = ('MERCHANTNUMBER', 'OPERATION', 'ORDERNUMBER', 'AMOUNT', 'CURRENCY', \
            'DEPOSITFLAG', 'MERORDERNUM', 'URL', 'DESCRIPTION',)
    _params_verify = ('MERCHANTNUMBER', 'OPERATION', 'ORDERNUMBER', 'AMOUNT', 'CURRENCY', \
            'DEPOSITFLAG', 'MERORDERNUM', 'MD', 'URL', 'PRCODE', 'SRCODE', 'RESULTTEXT', 'DESCRIPTION',)

    currency_code = {'czk':203}
    _host = None

    class Meta:
        verbose_name = _("Muzo configuration")
        verbose_name_plural = _("Muzo configurations")


    def _get_host(self):
        if not self._host:
            current_site = Site.objects.get_current()
            self._host = ('http://%s' % current_site.name).rstrip('/')

        return self._host

    def _set_host(self, value):
        self._host = value.rstrip('/')
    host = property(_get_host, _set_host)

    @staticmethod
    def is_muzo_paymenttype(payment_type):
        try:
            #TODO - refaktorovat
            return payment_type.code == payment_type.by_muzo().code
        except Exception as e:
            print e
            return False

    @staticmethod
    def get_default():
        if hasattr(settings, 'DEBUG_MUZO') and settings.DEBUG_MUZO:
            mc = MuzoConfiguration.objects.get(merchant_number=1)
        else:
            try:
                mc = MuzoConfiguration.objects.get(agency__name=settings.AGENCY_NAME)
            except:
                raise Exception('Undefined configuration for MUZO payment')
        
        return mc


    def get_order_number(self):
        pa = self.last_payment_attempt+1 if self.last_payment_attempt else 1
        self.last_payment_attempt = pa
        self.save()
        return pa

    def get_url_params_string_by_proform(self, proform):
        import urllib
        pars = self.get_url_params_by_proform(proform)
        str = ''
        for param in self._params_order:
            if str: str += '&'
            str += urllib.urlencode({param:pars[param]})
        for param in ['DIGEST']:
            if str: str += '&'
            str += urllib.urlencode({param:pars[param]})
        if self.default_lang:
            str += "&lang="+self.default_lang
        return str

    def get_url_params_by_proform(self, proform):
        """
        na zaklade proformy generuje parametry pro pozadavek v MUZO
        """
        from django.core.urlresolvers import reverse

        if not isinstance(proform, Proform):
            proform = Proform.objects.get(pk=proform)

        return self.get_url_params( \
            merchant_order_number=proform.vsymbol,\
            order_number=self.get_order_number(), \
            price=proform.price_total, \
            back_url=self.host + reverse('paymuzo.views.catch_proform_muzo_response' ,args=[proform.pk]), \
            description=self.get_description_by_proform(proform))

    def get_description_by_proform(self, proform):
        #momentalne pri nenastaveni description platba selze
        #return ""
        return "ProformPayment"

    def get_url_params(self, merchant_order_number, order_number, price, back_url="", description="", currency='czk'):
        """
        generuje parametry pro pozadavek v MUZO
        """
        if not self.currency_code.has_key(currency):
            raise Exception("Muzo doesnt support pay by currency:%s" % currency)
        if not price or not isinstance(price, Price) or price.is_null:
            raise Exception("Udefined price for pay")
        #
        params = {'MERCHANTNUMBER': self.merchant_number,
                  'OPERATION': "CREATE_ORDER",
                  'ORDERNUMBER': order_number,
                  'AMOUNT': "%d" % (100*price.incvat), #celociselna hodnota
                  'CURRENCY': self.currency_code.get(currency),
                  'DEPOSITFLAG': "1",
                  'MERORDERNUM': merchant_order_number,
                  'URL': back_url,
                  'DESCRIPTION': description
                  }
        params['DIGEST'] = self.create_digest(params)
        return params

        # NOTE: paypal format
        #for key, value in params.items():
        #    plaintext += u'%s=%s\n' % (key, value)

    def convert_params_for_digest(self, params):
        return '|'.join([str(params.get(x)) for x in self._params_order])

    def create_digest(self, params):
        plaintext = self.convert_params_for_digest(params)

        dgst = M2Crypto.EVP.MessageDigest("sha1")
        dgst.update(plaintext)

        key = str(self.merchant_private_key).replace("\r", "")

        pkey = M2Crypto.RSA.load_key_string(key)
        if not pkey.check_key():
            print('INVALID KEY')
#        signature = pkey.sign(plaintext)

        signature = pkey.sign(dgst.digest())

        return base64.b64encode(signature)


    def get_verify_params(self, data):
        pars = []
        for par in self._params_verify:
            pars.append(data.get(par) if data.has_key(par) else '')
        return '|'.join(pars)

    def verify_digest(self, request):
        """
        overuje podpis odpovedi z MUZO
        """
        data = request.GET

        digest = data.get('DIGEST')
        plaintext = self.get_verify_params(data)

        dgst = M2Crypto.EVP.MessageDigest("sha1")
        dgst.update(plaintext)

        key = str(self.muzo_public_key).replace("\r", "")

        buff = M2Crypto.BIO.MemoryBuffer(key)
        user_cert = M2Crypto.X509.load_cert_bio(buff)

        pub_key = user_cert.get_pubkey()
        pub_key.verify_init()
        pub_key.verify_update(plaintext)
        x = pub_key.verify_final(digest)
        print 'muzo verify: %d' % x
        return x


    def verify_proform_payment(self, request, proform=False):
        """
        overuje platbu na zaklade odpovedi z muza
        """
        if not self.verify_digest(request):
            print("Muzo payment is not veryfied")

        if not self.is_muzo_paymenttype(proform.payment_type):
            raise Exception('Proform has other payment type than MUZO')

        valid = self.set_attempt(request, proform)
        if valid:
            proform.is_paid = True
            proform.save()
            return True

        return False # platba probehla v poradku

    def set_attempt(self, request, proform):
        """vyhodnocuje pokus o zaplaceni"""
        data = request.GET
        pa = PaymentAttempt()
        pa.code = self.getkey(data, 'PRCODE')
        pa.subcode = self.getkey(data, 'SRCODE')
        pa.description = self.getkey(data, 'RESULTTEXT')
        pa.amount = self.getkey(data, 'AMOUNT', 0) / 100
        pa.attempt_id = self.getkey(data, 'ORDERNUMBER')
        pa.proform = proform
        pa.payment_type = self.payment_type
        if int(pa.code)==0 and int(pa.subcode)==0:
            pa.set_paid()
            status = True
        else:
            print ('Payment failed: %s - %s - %s' % (pa.code, pa.subcode, pa.description))
            pa.set_failed()
            status = False
        pa.save()

        return status

    @staticmethod
    def getkey(dict, key, default=None):
        #WUT? TODO: delete & refactor
        return dict[key] if dict.has_key(key) else default
    
    @staticmethod
    def get_proform_from_response(request, proform_id=None):
        """
        na zaklade odpovedi z muza urcuje placenou proformu
        """
        if not proform_id:
            proform_id=request.GET['proform_id']
        proform = Proform.objects.get(pk=proform_id)

        return proform
