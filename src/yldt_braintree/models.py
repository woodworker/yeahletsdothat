#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.db import models

class BrainTreeTransaction(models.Model):
    transaction_id = models.CharField(max_length=255)
    braintree_transaction_id = models.CharField(max_length=255)