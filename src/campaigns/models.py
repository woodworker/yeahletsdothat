#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import base64
import os

from django.db import models, IntegrityError
from django.contrib.auth.models import User
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from django.utils.encoding import python_2_unicode_compatible
from django_hstore.fields import DictionaryField


@python_2_unicode_compatible
class BankAccount(models.Model):
    user = models.ForeignKey(User)
    description = models.CharField(max_length=256, blank=True, null=True)
    btc_address = models.CharField(max_length=1024, blank=True, null=True)

    def __str__(self):
        if self.description and self.btc_address:
            return '{} ({})'.format(self.description, self.btc_address)
        elif not self.description and self.btc_address:
            return self.btc_address
        elif self.description and not self.btc_address:
            return self.description
        else:
            return _('Unnamed account')


def pkgen():
    """
    Generates the primary key codes for the Campaign class.
    """
    while True:
        new_key = base64.urlsafe_b64encode(os.urandom(12))
        # TODO: Filter rude words from generated
        if Campaign.objects.filter(key=new_key).count() == 0:
            return new_key

CURRENCY_EUR = (0, _('EUR'))
CURRENCY_USD = (1, _('USD'))
CURRENCY_BITCOIN = (2, _('BTC'))

CURRENCIES = (
    CURRENCY_EUR,
    CURRENCY_USD,
    CURRENCY_BITCOIN
)


@python_2_unicode_compatible
class Campaign(models.Model):
    """
    Campaign is the central piece of the model.
    """
    CURRENCIES = CURRENCIES
    key = models.CharField(max_length=16, null=True, default=pkgen)
    is_private = models.BooleanField(default=True)
    user = models.ForeignKey(User, null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    currency = models.IntegerField(choices=CURRENCIES)
    goal = models.DecimalField(max_digits=10, decimal_places=8)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    target_account = models.ForeignKey('BankAccount', null=True, blank=True)
    completed = models.BooleanField(default=False)

    @property
    def days_left(self):
        now = timezone.now()
        if now >= self.end_date:
            return 0

        delta = self.end_date - now
        return delta.days

    def get_number_of_participants(self):
        return self.transaction_set.filter(state=Transaction.STATE_PAYMENT_CONFIRMED).count()

    def get_total_pledge_amount(self):
        return self.transaction_set.filter(campaign=self,
            state=Transaction.STATE_PAYMENT_CONFIRMED).aggregate(Sum('amount'))['amount__sum']

    def __str__(self):
        return '{} ({})'.format(self.title, self.key)


@python_2_unicode_compatible
class Perk(models.Model):
    """
    Each campaign can have a number of perks.
    """
    campaign = models.ForeignKey('Campaign', related_name='perks')
    title = models.CharField(max_length=256)
    text = models.TextField(blank=True, null=True)
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    available = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return '{} ({})'.format(self.title, self.amount)


class Transaction(models.Model):
    STATE_ABORTED = -1
    STATE_PLEDGED = 0
    STATE_PAYMENT_RECEIVED = 1
    STATE_PAYMENT_CONFIRMED = 2

    STATES = (
        (STATE_PLEDGED, _("pledged")),
        (STATE_PAYMENT_RECEIVED, _('payment received')),
        (STATE_PAYMENT_CONFIRMED, _('payment confirmed'))
    )
    amount = models.DecimalField(max_digits=10, decimal_places=8, null=True)
    campaign = models.ForeignKey('Campaign', default=0)
    state = models.IntegerField(choices=STATES)

    btc_address = models.CharField(max_length=1024, blank=True, null=True)
    return_btc_address = models.CharField(max_length=1024, blank=True, null=True)

    email = models.EmailField(max_length=1024, blank=True, null=True)


class ProjectedModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        Disable the save method
        """
        return

    def delete(self, *args, **kwargs):
        """
        Disable the delete method.
        """
        return



class Event(models.Model):
    BEGIN_PAYMENT = 0
    EVENT_TYPES = (
        (BEGIN_PAYMENT, 'Begin payment process'),
    )
    event_type = models.IntegerField(choices=EVENT_TYPES)
    created = models.DateTimeField(auto_now_add=True)
    data = DictionaryField()