#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import uuid
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.generics import RetrieveAPIView, ListAPIView
from rest_framework.renderers import JSONRenderer
from django.utils.translation import ugettext as _
from rest_framework.response import Response
from campaigns.payment_method import get_method_by_name
from campaigns.utils import get_campaign_or_404, get_payment_methods
from django.conf import settings

import forms
from models import Campaign, Transaction, Perk
from commands import BeginPayment, ReceivePayment
from serializers import TransactionSerializer, PerkSerializer, PaymentMethodSerializer, \
    CampaignSerializer, PaymentPOSTData

logger = logging.getLogger(__name__)


def index(request):
    return render(request, 'campaigns/index.html', {})

def campaign_index(request):
    """
    Show the public campaigns in a list.
    """
    campaigns = Campaign.objects.filter(is_private=False)
    return render(request, 'campaigns/campaign_index.html', {'campaigns': campaigns})


def get_rpc_address():
    return "vla"

@login_required
def user_profile(request):
    campaigns = Campaign.objects.filter(user=request.user)
    return render(request, 'campaigns/user_profile.html', {'campaigns': campaigns})

def current_activities(request):
    pass

@login_required
def add_bankaccount(request):
    """
    TODO: Write docstring
    """
    if request.method == 'POST':
        form = forms.BankAccountForm(request.POST)
        if form.is_valid():
            new_account = form.save(commit=False)
            new_account.user = request.user
            new_account.save()
            return HttpResponseRedirect(reverse('manage_bankaccounts'))
        else:
            return render(request, 'campaigns/add_bankaccount.html', {'form': form})

    form = forms.BankAccountForm()
    return render(request, 'campaigns/add_bankaccount.html', {'form': form})

@login_required
def campaign_new(request):
    """
    Creates a new Campaign instance and then redirects the user to this
    campaign's edit page.
    """
    campaign = Campaign.objects.create(
        title=_('Unnamed Campaign'),
        currency=0, goal=1000, start_date=timezone.now(),
        end_date=timezone.now(), user=request.user)
    url = reverse('campaign_edit', args=[campaign.key])
    return HttpResponseRedirect(url)


def campaign_details(request, key):
    """
    View that shows a single activity.
    """
    logger.debug("campaign details")

    campaign = get_campaign_or_404(request, key)
    template_name = 'campaigns/campaign_details.html'

    if request.method == 'GET':
        if request.GET.get('embedded', None) is not None:
            template_name = 'campaigns/campaign_details_embedded.html'

    methods = get_payment_methods()
    supporters = Transaction.objects.filter(campaign=campaign, show_name=True)
    context = {'campaign': campaign, 'methods': methods, 'supporters': supporters}

    try:
        if settings.YLDT_PLEDGE_BUTTON_TEXT:
            context['pledge_button_text'] = settings.YLDT_PLEDGE_BUTTON_TEXT
    except AttributeError:
        pass
    return render(request, template_name, context)

@login_required
def campaign_edit(request, key):
    """
    Edit a campaign, basically delivers the angular app that changes the values via the
    REST backend.
    """
    campaign = get_campaign_or_404(request, key)
    rest_url = request.build_absolute_uri('/yeah/rest/campaigns/{}'.format(campaign.key))
    methods = get_payment_methods()
    currencies = [{'id': x[0], 'display_name': x[1]} for x in Campaign.CURRENCIES]
    campaign_ser = CampaignSerializer(campaign)
    initial_data = JSONRenderer().render(campaign_ser.data,
        accepted_media_type='application/json; indent=4')

    perk_ser = PerkSerializer(campaign.perks.all(), many=True)
    initial_perks = JSONRenderer().render(perk_ser.data,
        accepted_media_type='application/json; indent=4')

    context = {
        'rest_url': rest_url,
        'campaign': campaign,
        'methods': methods,
        'initial_data': initial_data,
        'initial_perks': initial_perks,
        'currencies': currencies,
    }

    return render(request, 'campaigns/campaign_edit.html', context)

@login_required
def campaign_show_transactions(request, key):
    """
    Show all the transactions of one campaign.
    """
    campaign = get_campaign_or_404(request, key)
    transactions = Transaction.objects.filter(campaign=campaign).order_by('started')

    context = {
        'campaign': campaign,
        'transactions': transactions
    }
    return render(request, 'campaigns/campaign_show_transactions.html', context)

def abort_activity(request, pk):
    """
    Abort an already started activity. If there are any already confirmed payments,
    they will be refunded.
    """
    # TODO: Implement abort feature
    return None

def select_payment(request, key):
    """
    The user has clicked the "Pledge now" button. Let's show him the list of
    available Payment methods
    """
    campaign = get_campaign_or_404(request, key)
    perk_id = request.GET.get('perk', None)
    pledge_value = Decimal('0.0')
    perk = None
    if perk_id != None:
        perk = get_object_or_404(Perk, pk=int(perk_id))
        pledge_value = perk.amount

    methods = get_payment_methods()

    context = {
        'campaign': campaign,
        'selected_perk': perk,
        'methods': methods,
        'pledge_value': pledge_value,
    }

    if request.method == 'POST':
        form = forms.SelectPaymentForm(campaign, perk, request.POST)
        if form.is_valid():
            amount = form.cleaned_data.get('amount')
            payment_method_name= form.cleaned_data.get('payment_method')
            method = get_method_by_name(payment_method_name)
            email = form.cleaned_data.get('email1')
            name = form.cleaned_data.get('name')
            show_name = not form.cleaned_data['hide_name']

            # Create a new payment transaction with a random ID.
            transaction_id = str(uuid.uuid4())
            perk_id = None
            if perk != None:
                perk_id = perk.id
            BeginPayment(transaction_id, campaign.key, amount, email, perk_id,
                name, show_name, payment_method_name)

            # Delegate the payment transaction to the pay() method of the selected
            # payment method. The method will then redirect the user to the page it needs
            # to complete the payment.
            return method.pay(request, campaign, transaction_id)

        else:
            return render(request, 'campaigns/select_payment.html', dict(context, form=form))

    else:
        return render(request, 'campaigns/select_payment.html', context)

def transaction(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk)
    return render(request, 'campaigns/transaction.html',
            {'transaction': transaction, 'activity': transaction.campaign})


class CampaignListAPI(ListAPIView):
    queryset = Campaign.objects.filter(is_private=False)
    serializer_class = CampaignSerializer


class CampaignRetrieveAPI(RetrieveAPIView):
    """

    """
    serializer_class = CampaignSerializer
    lookup_field = 'key'
    queryset = Campaign.objects.all()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={'request': request})
        return Response(serializer.data)

@api_view()
def list_payment_methods(request, key):
    campaign = get_object_or_404(Campaign, key=key)
    methods = get_payment_methods()
    ser_methods = PaymentMethodSerializer(methods, many=True,
        context={'request': request, 'key': key})
    return Response(ser_methods.data)

@api_view(['GET'])
def pay_with(request, key, name):
    campaign = get_object_or_404(Campaign, key=key)
    method = get_method_by_name(name)

    return Response(method.get_json())

@api_view(['POST'])
def post_transaction(request, key):
    if request.method == 'POST':
        ser = PaymentPOSTData(data=request.data)
        if ser.is_valid():
            logger.debug('data is ' + str(ser.data))
            amount = ser.validated_data.get('amount')
            payment_method_name = ser.validated_data.get('name')
            method = get_method_by_name(payment_method_name)
            payment_nonce = ser.validated_data.get('payment_nonce')
            name = "Urongo Krompf"
            email = "me@uwekamper.de" # ser.validated_data.get('email1')
            show_name = True # not ser.validated_data['hide_name']

            # Create a new payment transaction with a random ID.
            transaction_id = str(uuid.uuid4())
            perk_id = None
            # if perk != None:
            #     perk_id = perk.id
            BeginPayment(transaction_id, key, amount, email, perk_id, name, show_name,
                    payment_method_name)
            transaction = Transaction.objects.get(transaction_id=transaction_id)

            if method.validate_nonce(amount, payment_nonce):
                logger.debug('transaction is good')
                ReceivePayment(transaction_id, amount, request)
                return Response(TransactionSerializer(transaction).data)
            else:
                logger.debug('transaction is bad')
                return Response(TransactionSerializer(transaction).data)
        else:
            logger.debug("got a wrong http method")
            return Response({'result': 'error', 'errors': ser.errors})

# TODO: Move this into the bitcoin module
# @api_view(['GET'])
# def transaction_api(request, pk):
#     transaction = get_object_or_404(TransactionState, pk=pk)
#     s = jsonrpclib.Server(get_rpc_address())
#     received = s.getreceivedbyaddress(transaction.btc_address, 0)
#     confirmed = s.getreceivedbyaddress(transaction.btc_address, 1)
#
#     print "received: ", received
#     print "confirmed: ", confirmed
#
#     # TODO: this should be moved into a background task
#     if transaction.state == TransactionState.STATE_PLEDGED:
#         if received >= float(transaction.amount):
#             transaction.state = Transaction.STATE_PAYMENT_RECEIVED
#             transaction.save()
#         if confirmed >= float(transaction.amount):
#             transaction.state = Transaction.STATE_PAYMENT_CONFIRMED
#             transaction.save()
#     elif transaction.state == Transaction.STATE_PAYMENT_RECEIVED:
#         if confirmed >= float(transaction.amount):
#             transaction.state = Transaction.STATE_PAYMENT_CONFIRMED
#             transaction.save()
#
#     check_completion(transaction.campaign)
#
#     # transaction.state = 0
#     ser = TransactionSerializer(transaction)
#     return Response(ser.data)

