"""Settlement-backed wallet and a reviewable withdrawal queue; no implicit transfers."""
import re
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.views import PlatformPermission
from apps.checkout.models import Order

from .management_api import access, audit
from .models import Business, WalletSettlement, Withdrawal


def live_orders(business):
    return Order.objects.filter(business=business, currency=business.currency, status='paid',
                                payment_backend='venty', provider='mpesa', payment_review_required=False)


def total(rows, field='amount'):
    return rows.aggregate(value=Sum(field))['value'] or Decimal('0.00')


def wallet_totals(business):
    credits = WalletSettlement.objects.filter(business=business, currency=business.currency)
    withdrawals = Withdrawal.objects.filter(business=business, currency=business.currency)
    settled = total(credits)
    reserved = total(withdrawals.filter(status='pending'))
    withdrawn = total(withdrawals.filter(status='completed'))
    # Gross received is reported separately: only reconciled net settlement is available.
    return {'currency': business.currency, 'collected': str(total(live_orders(business), 'total')),
            'awaiting_settlement': str(total(live_orders(business).filter(walletsettlement__isnull=True), 'total')),
            'settled': str(settled), 'reserved': str(reserved), 'withdrawn': str(withdrawn),
            'available': str(max(Decimal('0.00'), settled - reserved - withdrawn)),
            'test_payments': str(total(Order.objects.filter(business=business, currency=business.currency, status='paid').exclude(payment_backend='venty'), 'total'))}


class WithdrawalSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='business.name', read_only=True)

    class Meta:
        model = Withdrawal
        fields = ['id', 'business_id', 'business_name', 'amount', 'currency', 'method', 'recipient_name', 'phone', 'bank_name', 'account_number', 'status', 'transfer_reference', 'review_note', 'created_at', 'reviewed_at']
        read_only_fields = fields


class WithdrawalInput(serializers.Serializer):
    request_key = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    method = serializers.ChoiceField(choices=['mpesa', 'bank'])
    recipient_name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default='')
    bank_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default='')
    account_number = serializers.CharField(max_length=80, required=False, allow_blank=True, default='')

    def validate(self, data):
        if data['method'] == 'mpesa':
            phone = re.sub(r'[\s()+-]', '', data['phone'])
            if re.fullmatch(r'0[17]\d{8}', phone):
                phone = '254' + phone[1:]
            if not re.fullmatch(r'254[17]\d{8}', phone):
                raise ValidationError({'phone': 'Enter a Kenyan mobile number.'})
            if data['amount'] != data['amount'].to_integral_value():
                raise ValidationError({'amount': 'Enter a whole-shilling amount for M-Pesa.'})
            data.update(phone=phone, bank_name='', account_number='')
        elif not data['bank_name'] or not data['account_number']:
            raise ValidationError('Enter the bank name and account number.')
        else:
            data['phone'] = ''
        return data


class WalletView(APIView):
    @extend_schema(responses={200: {'type': 'object'}})
    def get(self, request, business_id):
        business = access(request, business_id, ['owner'])
        return Response({**wallet_totals(business), 'withdrawals': WithdrawalSerializer(Withdrawal.objects.filter(business=business).select_related('business')[:50], many=True).data})

    @extend_schema(request=WithdrawalInput, responses={201: WithdrawalSerializer})
    @transaction.atomic
    def post(self, request, business_id):
        access(request, business_id, ['owner'])
        business = Business.objects.select_for_update().get(pk=business_id)
        data = WithdrawalInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        existing = Withdrawal.objects.filter(business=business, request_key=values['request_key']).first()
        if existing:
            if any(getattr(existing, key) != value for key, value in values.items()):
                raise ValidationError('This withdrawal reference has already been used.')
            return Response(WithdrawalSerializer(existing).data)
        if values['method'] == 'mpesa' and business.currency != 'KES':
            raise ValidationError('M-Pesa withdrawals require a KES wallet.')
        if business.currency in {'UGX', 'RWF'} and values['amount'] != values['amount'].to_integral_value():
            raise ValidationError('This wallet requires whole-unit withdrawals.')
        if values['amount'] > Decimal(wallet_totals(business)['available']):
            raise ValidationError({'amount': 'Amount exceeds your available settled balance.'})
        withdrawal = Withdrawal.objects.create(business=business, requested_by=request.user, currency=business.currency, **values)
        audit(request, business, 'wallet.withdrawal_requested', withdrawal.pk)
        return Response(WithdrawalSerializer(withdrawal).data, status=201)


class CancelWithdrawalView(APIView):
    @extend_schema(request=None, responses=WithdrawalSerializer)
    @transaction.atomic
    def post(self, request, business_id, withdrawal_id):
        business = access(request, business_id, ['owner'])
        Business.objects.select_for_update().get(pk=business_id)
        withdrawal = get_object_or_404(Withdrawal, business=business, pk=withdrawal_id)
        if withdrawal.status != 'pending':
            raise ValidationError('Only a pending withdrawal can be cancelled.')
        withdrawal.status = 'cancelled'
        withdrawal.reviewed_at = timezone.now()
        withdrawal.save(update_fields=['status', 'reviewed_at'])
        audit(request, business, 'wallet.withdrawal_cancelled', withdrawal.pk)
        return Response(WithdrawalSerializer(withdrawal).data)


class SettlementInput(serializers.Serializer):
    order_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    reference = serializers.CharField(max_length=200)


class WithdrawalReviewInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=['completed', 'rejected'])
    transfer_reference = serializers.CharField(max_length=200, allow_blank=True, default='')
    review_note = serializers.CharField(max_length=500, allow_blank=True, default='')

    def validate(self, data):
        if data['status'] == 'completed' and not data['transfer_reference']:
            raise ValidationError('Enter the confirmed transfer reference before recording completion.')
        if data['status'] == 'rejected' and not data['review_note']:
            raise ValidationError('Enter the reason for rejecting the request.')
        return data


class PlatformWalletView(APIView):
    permission_classes = [PlatformPermission]

    @extend_schema(responses={200: {'type': 'object'}})
    def get(self, request):
        pending = Withdrawal.objects.filter(status='pending').select_related('business')[:100]
        orders = Order.objects.filter(status='paid', payment_backend='venty', provider='mpesa', payment_review_required=False, walletsettlement__isnull=True).select_related('business').order_by('-created_at')[:100]
        return Response({'withdrawals': WithdrawalSerializer(pending, many=True).data,
                         'settlements': [{'order_id': str(o.pk), 'business': o.business.name, 'amount': str(o.total), 'currency': o.currency} for o in orders]})

    @extend_schema(request=SettlementInput, responses={201: {'type': 'object'}})
    @transaction.atomic
    def post(self, request):
        data = SettlementInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        order = get_object_or_404(Order, pk=values['order_id'])
        business = Business.objects.select_for_update().get(pk=order.business_id)
        if business.suspended or not live_orders(business).filter(pk=order.pk).exists():
            raise ValidationError('Only verified live payments in the current wallet currency can be settled.')
        if WalletSettlement.objects.filter(order=order).exists():
            raise ValidationError('This order has already been settled.')
        if values['amount'] > order.total:
            raise ValidationError('Net settlement cannot exceed the collected amount.')
        settlement = WalletSettlement.objects.create(business=business, order=order, amount=values['amount'], currency=order.currency, reference=values['reference'], recorded_by=request.user)
        audit(request, business, 'wallet.settlement_recorded', settlement.pk)
        return Response({'id': str(settlement.pk)}, status=201)


class PlatformWithdrawalReviewView(APIView):
    permission_classes = [PlatformPermission]

    @extend_schema(request=WithdrawalReviewInput, responses=WithdrawalSerializer)
    @transaction.atomic
    def post(self, request, withdrawal_id):
        data = WithdrawalReviewInput(data=request.data)
        data.is_valid(raise_exception=True)
        withdrawal = get_object_or_404(Withdrawal, pk=withdrawal_id)
        Business.objects.select_for_update().get(pk=withdrawal.business_id)
        withdrawal.refresh_from_db()
        if withdrawal.status != 'pending':
            raise ValidationError('This withdrawal has already been reviewed.')
        if withdrawal.business.suspended:
            raise ValidationError('This store is suspended.')
        for key, value in data.validated_data.items():
            setattr(withdrawal, key, value)
        withdrawal.reviewed_by = request.user
        withdrawal.reviewed_at = timezone.now()
        withdrawal.save()
        audit(request, withdrawal.business, 'wallet.withdrawal_' + withdrawal.status, withdrawal.pk)
        return Response(WithdrawalSerializer(withdrawal).data)
