# ruff: noqa: F401, F811
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.businesses.models import AuditEvent, Business, Membership, WalletSettlement, Withdrawal
from tests.test_foundation import (
    application,
    business,
    client,
    login,
    mutate,
    owner,
    reset_throttles,
    staff,
    staff_login,
)
from tests.test_management import colleague, make_order

pytestmark = pytest.mark.django_db


def endpoint(business):
    return f'/api/businesses/{business.pk}/payments/wallet/'


def request(amount='60', **changes):
    return {'request_key': str(uuid.uuid4()), 'amount': amount, 'method': 'mpesa', 'recipient_name': 'Test recipient', 'phone': '0712345678', **changes}


def settle(business, staff, amount='100'):
    order = make_order(business, payment_backend='venty')
    return WalletSettlement.objects.create(business=business, order=order, amount=amount, currency='KES', reference='SETTLED-FIXTURE', recorded_by=staff)


def test_wallet_requires_owner_and_filters_live_funds(client, owner, staff, business):
    make_order(business, payment_backend='stripe')
    make_order(business, payment_backend='simulator')
    make_order(business, payment_backend='venty', payment_review_required=True)
    make_order(business, payment_backend='venty', status='pending')
    make_order(business, payment_backend='venty')
    settle(business, staff, '90')
    login(client, owner)
    wallet = client.get(endpoint(business)).json()
    assert Decimal(wallet['collected']) == Decimal('200')
    assert Decimal(wallet['awaiting_settlement']) == Decimal('100')
    assert Decimal(wallet['available']) == Decimal('90')
    helper = colleague()
    Membership.objects.create(business=business, user=helper, role='manager')
    login(client, helper)
    assert client.get(endpoint(business)).status_code == 403
    assert mutate(client, endpoint(business), request()).status_code == 403


def test_withdrawal_reserves_balance_is_idempotent_and_cannot_overspend(client, owner, staff, business):
    settle(business, staff)
    login(client, owner)
    data = request()
    assert client.post(endpoint(business), data, format='json').status_code == 403
    first = mutate(client, endpoint(business), data)
    assert first.status_code == 201, first.data
    assert first.data['phone'] == '254712345678'
    again = mutate(client, endpoint(business), data)
    assert again.status_code == 200 and again.data['id'] == first.data['id']
    assert mutate(client, endpoint(business), {**data, 'amount': '61'}).status_code == 400
    assert mutate(client, endpoint(business), request('41')).status_code == 400
    wallet = client.get(endpoint(business)).json()
    assert Decimal(wallet['reserved']) == Decimal('60') and Decimal(wallet['available']) == Decimal('40')
    assert Withdrawal.objects.count() == 1
    assert AuditEvent.objects.filter(action='wallet.withdrawal_requested').count() == 1


def test_cancel_releases_funds_and_cannot_cancel_another_store(client, owner, staff, business):
    settle(business, staff)
    login(client, owner)
    row = mutate(client, endpoint(business), request()).json()
    other = Business.objects.create(name='Other', slug='other', currency='KES', country='KE')
    Membership.objects.create(business=other, user=owner, role='owner')
    assert mutate(client, f'/api/businesses/{other.pk}/payments/withdrawals/{row["id"]}/cancel/').status_code == 404
    url = f'/api/businesses/{business.pk}/payments/withdrawals/{row["id"]}/cancel/'
    assert mutate(client, url).status_code == 200
    assert mutate(client, url).status_code == 400
    assert Decimal(client.get(endpoint(business)).json()['available']) == Decimal('100')


def test_invalid_withdrawal_details_and_unsettled_money_rejected(client, owner, business):
    make_order(business, payment_backend='venty')
    login(client, owner)
    for data in [request(), request('-1'), request('0'), request('1.50'), request('10', phone='bad'), request('10', method='bank')]:
        assert mutate(client, endpoint(business), data).status_code == 400
    assert not Withdrawal.objects.exists()


def test_platform_reconciles_settlement_and_records_withdrawal_outcome(client, owner, staff, business):
    order = make_order(business, payment_backend='venty')
    login(client, owner)
    assert client.get('/api/platform/wallet/').status_code == 403
    platform = APIClient(enforce_csrf_checks=True)
    staff_login(platform, staff)
    payload = {'order_id': str(order.pk), 'amount': '95', 'reference': 'SETTLEMENT-001'}
    assert mutate(platform, '/api/platform/wallet/', {**payload, 'amount': '101'}).status_code == 400
    assert mutate(platform, '/api/platform/wallet/', payload).status_code == 201
    assert mutate(platform, '/api/platform/wallet/', payload).status_code == 400
    login(client, owner)
    row = mutate(client, endpoint(business), request('90')).json()
    url = f'/api/platform/withdrawals/{row["id"]}/review/'
    assert mutate(platform, url, {'status': 'completed'}).status_code == 400
    assert mutate(platform, url, {'status': 'completed', 'transfer_reference': 'TRANSFER-001'}).status_code == 200
    assert mutate(platform, url, {'status': 'rejected', 'review_note': 'Duplicate'}).status_code == 400
    login(client, owner)
    wallet = client.get(endpoint(business)).json()
    assert Decimal(wallet['available']) == Decimal('5') and Decimal(wallet['withdrawn']) == Decimal('90') and Decimal(wallet['reserved']) == Decimal('0.00')


def test_platform_rejects_test_settlements_and_rejection_releases_reserve(client, owner, staff, business):
    test_order = make_order(business, payment_backend='stripe')
    settle(business, staff)
    login(client, owner)
    row = mutate(client, endpoint(business), request()).json()
    staff_login(client, staff)
    assert mutate(client, '/api/platform/wallet/', {'order_id': str(test_order.pk), 'amount': '50', 'reference': 'TEST'}).status_code == 400
    assert mutate(client, f'/api/platform/withdrawals/{row["id"]}/review/', {'status': 'rejected', 'review_note': 'Recipient needs correction'}).status_code == 200
    login(client, owner)
    assert Decimal(client.get(endpoint(business)).json()['available']) == Decimal('100')


def test_suspended_store_cannot_withdraw(client, owner, staff, business):
    settle(business, staff)
    business.suspended = True
    business.save()
    login(client, owner)
    assert mutate(client, endpoint(business), request()).status_code == 403


@patch('apps.businesses.payment_settings.signed_post', return_value={'stripe': {'secret_key_saved': True, 'enabled': True}})
def test_settings_proxy_scopes_store_and_owner_and_avoids_secret_audit(provider, client, owner, business):
    login(client, owner)
    url = f'/api/businesses/{business.pk}/payments/configuration/'
    business.store_settings.stripe_enabled = False
    business.store_settings.save()
    payload = {'business_id': str(uuid.uuid4()), 'provider': 'stripe', 'values': {'enabled': True, 'secret_key': 'sk_test_fixture'}}
    assert mutate(client, url, payload, method='patch').status_code == 200
    assert provider.call_args.args[1]['business_id'] == str(business.pk)
    business.store_settings.refresh_from_db()
    assert business.store_settings.stripe_enabled is True
    audit = AuditEvent.objects.get(action='payments.configuration_updated')
    assert audit.detail == {} and 'sk_test' not in audit.object_id
    helper = colleague()
    Membership.objects.create(business=business, user=helper, role='manager')
    login(client, helper)
    assert client.get(url).status_code == 200
    assert mutate(client, url, payload, method='patch').status_code == 403
