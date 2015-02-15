#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import uuid

from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
import jsonrpclib
from rest_framework.decorators import api_view
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from campaigns.payment_method import get_method_by_name
from campaigns.serializers import TransactionSerializer, CampaignSerializer, PerkSerializer
from campaigns.utils import get_campaign_or_404, get_payment_methods
from django.conf import settings

import forms
from models import Campaign, BankAccount, Transaction

from commands import begin_payment

def index(request):
    return render(request, 'campaigns/index.html', {})

def get_rpc_address():
    return "vla"

@login_required
def user_profile(request):
    campaigns = Campaign.objects.filter(user=request.user)
    accounts = BankAccount.objects.filter(user=request.user)
    return render(request, 'campaigns/user_profile.html',
        {'accounts': accounts, 'campaigns': campaigns})

def current_activities(request):
    pass

@login_required
def manage_bankaccounts(request):
    accounts = BankAccount.objects.filter(user=request.user)
    return render(request, 'campaigns/manage_bankaccounts.html', {'accounts': accounts})

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
def new_activity(request):
    """
    View for creating new activities.
    """
    # if request.method == 'POST':
    #     form = forms.NewCampaignForm(request.user, request.POST)
    #     if form.is_valid():
    #         new_campaign = form.save(commit=False)
    #         new_campaign.user = request.user
    #         new_campaign.save()
    #         url = reverse('campaign_details', args=(new_campaign.key,))
    #         return HttpResponseRedirect(url)
    #     else:
    #         print form.errors
    #         return render(request, 'campaigns/new_campaign.html', {'form': form})

    form = forms.NewCampaignForm(user=request.user)
    return render(request, 'campaigns/new_campaign.html', {'form': form})


def campaign_details(request, key):
    """
    View that shows a single activity.
    """
    campaign = get_campaign_or_404(request, key)
    methods = get_payment_methods()
    context = {'campaign': campaign, 'methods': methods, }

    try:
        if settings.YLDT_PLEDGE_BUTTON_TEXT:
            context['pledge_button_text'] = settings.YLDT_PLEDGE_BUTTON_TEXT
    except AttributeError:
        pass

    return render(request, 'campaigns/campaign_details.html', context)

def campaign_edit(request, key):
    """
    Edit a campaign, basically delivers the angular app that changes the values via the
    REST backend.
    """
    campaign = get_campaign_or_404(request, key)
    methods = get_payment_methods()
    currencies = [{'id': x[0], 'display_name': x[1]} for x in Campaign.CURRENCIES]
    campaign_ser = CampaignSerializer(campaign)
    initial_data = JSONRenderer().render(campaign_ser.data,
        accepted_media_type='application/json; indent=4')

    perk_ser = PerkSerializer(campaign.perks.all(), many=True)
    initial_perks = JSONRenderer().render(perk_ser.data,
        accepted_media_type='application/json; indent=4')

    context = {
        'campaign': campaign,
        'methods': methods,
        'initial_data': initial_data,
        'initial_perks': initial_perks,
        'currencies': currencies,
    }

    return render(request, 'campaigns/campaign_edit.html', context)

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

    # TODO: is this necessary?
    methods = get_payment_methods()

    if request.method == 'POST':
        form = forms.SelectPaymentForm(campaign, request.POST)
        if form.is_valid():
            amount = form.cleaned_data.get('amount')
            method = get_method_by_name(form.cleaned_data.get('payment_method'))
            email = form.cleaned_data.get('email1')

            # Create a new payment transaction with a random ID.
            transaction_id = str(uuid.uuid4())
            begin_payment(transaction_id, campaign.key, amount, email)

            # Delegate the payment transaction to the pay() method of the selected
            # payment method. The method will then redirect the user to the page it needs
            # to complete the payment.
            return method.pay(campaign, transaction_id)

        else:
            return render(request, 'campaigns/select_payment.html',
                    {'campaign': campaign, 'methods': methods, 'form': form})

    else:
        return render(request, 'campaigns/select_payment.html',
                {'campaign': campaign, 'methods': methods})

def transaction(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk)
    return render(request, 'campaigns/transaction.html',
            {'transaction': transaction, 'activity': transaction.campaign})

def check_completion(activity):
    amount = activity.get_total_pledge_amount()

    if amount >= activity.goal and not activity.completed:
        # set the activity to completed so no one else can pledge.
        activity.completed = True
        activity.save()

        s = jsonrpclib.Server(get_rpc_address())
        s.sendtoaddress(activity.target_account.btc_address, float(activity.goal),
            'buy-uk-a-beer')


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

