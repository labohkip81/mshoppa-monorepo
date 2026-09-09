import { Component, inject, signal } from '@angular/core';
import { CurrencyPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient } from '@angular/common/http';
import { Api, errorMessage } from '@mshoppa/api';
import { Icon, Logo, Button } from '@mshoppa/ui';
import { PaymentCheckout } from './checkout';

interface Session { order_number:string; store_name:string; provider:string; amount:string; currency:string; status:string; order_status:string; delivered:boolean; expired:boolean; return_url:string; backend:string; provider_ready:boolean; initiation_state:string; external_id:string; redirect_url:string; receipt_number:string }
@Component({selector:'mshoppa-root',standalone:true,imports:[CurrencyPipe,FormsModule,Icon,Logo,Button,PaymentCheckout],template:`
@if (checkoutToken && !token) { <m-payment-checkout /> } @else { <main class="payment-page"><m-logo /><div class="payment-icon"><m-icon name="shield" /></div>
@if (session(); as payment) {
  <h1>{{ payment.provider === 'stripe' ? 'Pay by card' : 'Pay with M-Pesa' }}</h1><p>{{ payment.store_name }} · Order #{{ payment.order_number }}</p><h2>{{ payment.amount | currency:payment.currency:'code' }}</h2>
  <div class="notice">{{ payment.backend === 'simulator' ? 'Local simulator — no money is collected.' : payment.backend === 'stripe' ? 'Stripe test mode — use a test card. No real charges.' : 'M-Pesa via Venty — approving the prompt on your phone sends a real payment.' }}</div>
  @if (error()) { <p class="notice error" role="alert">{{ error() }}</p> }
  @if (payment.delivered) {
    <p role="status">{{ payment.order_status === 'paid' ? 'Payment confirmed. Thank you!' : payment.status === 'succeeded' ? 'Payment received after the order closed. Contact the store to arrange fulfillment or a refund.' : 'Payment unsuccessful. Return to the shop to try again.' }}</p>
    @if (payment.receipt_number) { <p>Receipt: {{ payment.receipt_number }}</p> }
  } @else if (payment.status !== 'pending') {
    <p>Your payment result is saved. Update the order to finish.</p><button mButton [disabled]="busy()" (click)="payment.backend === 'simulator' ? simulate(payment.status) : refresh()">Update order</button>
  } @else if (payment.backend === 'simulator') {
    @if (payment.expired) { <p>This session has expired. Return to the shop to start again.</p> } @else { <div class="payment-test-actions"><button mButton [disabled]="busy()" (click)="simulate('succeeded')">Simulate success</button><button mButton class="secondary" [disabled]="busy()" (click)="simulate('failed')">Simulate failure</button></div> }
  } @else if (!payment.provider_ready) {
    <p role="status">{{ payment.backend === 'stripe' ? 'Card payments are awaiting Stripe test configuration.' : 'M-Pesa is awaiting store payment configuration.' }} Contact the store or return to your order.</p>
  } @else if (payment.external_id || payment.initiation_state !== 'new') {
    @if (payment.backend === 'stripe' && payment.redirect_url && !payment.expired) { <a mButton [href]="payment.redirect_url">Continue to Stripe</a> }
    @if (payment.backend === 'venty') { <p>{{ payment.initiation_state === 'unknown' ? 'The request could not be confirmed. Do not start another payment until the store has checked it.' : 'Complete the M-Pesa prompt on your phone, then check your payment.' }}</p> }
    <button mButton class="secondary" [disabled]="busy()" (click)="refresh()">{{ busy() ? 'Checking…' : 'Check payment status' }}</button>
    @if (checked() && payment.status === 'pending') { <p role="status">Payment confirmation is still pending.</p> }
  } @else if (payment.expired) { <p>This session has expired. Return to the shop to start again.</p>
  } @else if (payment.backend === 'stripe') {
    <p>Use test card <strong>4242 4242 4242 4242</strong>, any future expiry date and any three-digit CVC on Stripe’s secure checkout.</p>
    <button mButton [disabled]="busy()" (click)="start()">{{ busy() ? 'Opening Stripe…' : 'Continue to Stripe test checkout' }}</button>
  } @else {
    <form (ngSubmit)="start()" ngNativeValidate class="payment-phone-form"><label>M-Pesa phone number<input type="tel" name="phone" [(ngModel)]="phone" placeholder="0712 345 678" autocomplete="tel" required [disabled]="busy()"></label><button mButton [disabled]="busy()">{{ busy() ? 'Sending request…' : 'Send M-Pesa prompt' }}</button></form>
  }
  <p><a class="text-link" [href]="payment.return_url">View order & tracking →</a></p>
} @else { <h1>{{ loading() ? 'Opening payment…' : 'No active payment session' }}</h1><p>{{ error() || 'Start checkout from a store.' }}</p> }
<footer>Enter card details only on Stripe. Enter an M-Pesa PIN only on your phone’s M-Pesa prompt.</footer></main> }`})
class PaymentsRoot {
  api=inject(Api); session=signal<Session|null>(null); error=signal(''); busy=signal(false); loading=signal(true); checked=signal(false); phone='';
  token=new URLSearchParams(location.search).get('session');
  checkoutToken=new URLSearchParams(location.search).get('checkout');
  constructor() { void this.load().then(()=>{ if(new URLSearchParams(location.search).has('returned') && this.session()?.backend === 'stripe') void this.refresh(); }); }
  path(action='') { return `sessions/${encodeURIComponent(this.token!)}/${action ? action+'/' : ''}`; }
  async load() { try { if(this.token) this.session.set(await this.api.get<Session>(this.path())); } catch(e) { this.error.set(errorMessage(e)); } finally { this.loading.set(false); } }
  async action(action:string,payload:unknown={}) {
    if(!this.token || this.busy()) return null;
    this.busy.set(true); this.error.set('');
    try { const payment=await this.api.send<Session>('POST',this.path(action),payload); this.session.set(payment); return payment; }
    catch(e) { this.error.set(errorMessage(e)); await this.load(); return null; }
    finally { this.busy.set(false); }
  }
  async start() { const payment=await this.action('start',{phone:this.phone}); if(payment?.backend === 'stripe' && payment.redirect_url.startsWith('https://checkout.stripe.com/')) location.assign(payment.redirect_url); }
  async refresh() { await this.action('refresh'); this.checked.set(true); }
  async simulate(status:string) { await this.action('simulate',{status}); }
}
bootstrapApplication(PaymentsRoot,{providers:[provideHttpClient()]}).catch(console.error);
