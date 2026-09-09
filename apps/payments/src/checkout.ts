import { Component, inject, signal } from '@angular/core';
import { CurrencyPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Api, errorMessage } from '@mshoppa/api';
import { Button, Icon, Logo } from '@mshoppa/ui';

interface CheckoutOrder { payment_url:string; return_url:string; status:string }
interface Checkout { order_number:string; store_name:string; return_url:string; currency:string; subtotal:string; tax:string; total:string; tax_rate:string; quote_token:string; methods:string[]; providers:Record<string,{backend:string;ready:boolean;mode:string}>; lines:{image_url:string;variant_id:string;product_name:string;variant_name:string;quantity:number;line_total:string}[]; order?:CheckoutOrder }

@Component({selector:'m-payment-checkout',standalone:true,imports:[FormsModule,CurrencyPipe,Button,Icon,Logo],template:`
<main class="payment-checkout"><header class="payment-checkout-header"><m-logo /><span><m-icon name="shield" />Secure checkout</span></header>
@if (checkout(); as cart) {
  <a class="text-link" [href]="cart.return_url">← Back to {{ cart.store_name }}</a>
  <h1>Checkout</h1><p class="payment-checkout-intro">A few details, then you’re ready to pay.</p>
  @if (error()) { <div class="notice error" role="alert">{{ error() }} <button type="button" class="text-link" (click)="load()" [disabled]="busy()">Refresh totals</button></div> }
  <div class="payment-checkout-grid"><form ngNativeValidate (ngSubmit)="placeOrder()" class="checkout-details">
    <fieldset [disabled]="busy()"><legend>Contact & delivery</legend>
      <div class="checkout-contact-grid"><label>Full name<input name="name" [(ngModel)]="form.name" autocomplete="name" required maxlength="150" placeholder="Your full name"></label><label>Email address<input name="email" [(ngModel)]="form.email" type="email" autocomplete="email" required maxlength="254" placeholder="you@example.com"></label></div>
      <label>Phone number<input name="phone" [(ngModel)]="form.phone" type="tel" autocomplete="tel" maxlength="30" [required]="form.provider === 'mpesa'" placeholder="0712 345 678"></label>
      <label>Delivery address<textarea name="address" [(ngModel)]="form.address" autocomplete="street-address" rows="3" required maxlength="500" placeholder="Street, building, town and delivery instructions"></textarea></label>
    </fieldset>
    <fieldset [disabled]="busy()"><legend>Payment method</legend><p class="checkout-method-hint">Choose how you’d like to pay.</p>
      @for (method of cart.methods; track method) { <label class="checkout-payment-option" [class.selected]="form.provider === method"><input type="radio" name="provider" [value]="method" [(ngModel)]="form.provider" required><span class="checkout-provider-logo"><img [src]="method === 'stripe' ? '/brand/payments/stripe.svg' : '/brand/payments/mpesa.png'" [alt]="method === 'stripe' ? 'Stripe' : 'M-Pesa'" [class.mpesa-logo]="method === 'mpesa'"></span><span><strong>{{ method === 'stripe' ? 'Card' : 'M-Pesa' }}</strong><small>{{ cart.providers[method]?.backend === 'simulator' ? 'Local test payment' : method === 'stripe' ? 'Visa, Mastercard and more · Stripe test mode' : 'Approve the payment on your phone' }}</small></span></label> }
      @if (!cart.methods.length) { <p class="notice">This store has no payment methods enabled.</p> }
    </fieldset>
    <button mButton class="checkout-submit" [disabled]="busy() || !cart.methods.length">{{ busy() ? 'Preparing your order…' : 'Continue to payment' }} <m-icon name="arrow" /></button>
    <p class="checkout-safe-note">Review and confirm your payment in the next step.</p>
  </form><aside class="payment-order-summary"><div class="payment-summary-title"><h2>Order summary</h2><strong class="checkout-order-number">Order #{{ cart.order_number }}</strong><span>{{ cart.store_name }}</span></div>
    @for (line of cart.lines; track line.variant_id) { <div class="payment-summary-line"><span class="checkout-item-icon">@if (imageUrl(line.image_url,cart.return_url); as image) { <img [src]="image" [alt]="line.product_name" width="52" height="60" decoding="async" (error)="imageFailed(line.image_url)"> } @else { <m-icon name="box" /> }</span><div><strong>{{ line.product_name }}</strong><small>{{ line.variant_name !== 'Default' ? line.variant_name + ' · ' : '' }}Qty {{ line.quantity }}</small></div><span>{{ line.line_total | currency:cart.currency:'code' }}</span></div> }
    <dl><div><dt>Subtotal</dt><dd>{{ cart.subtotal | currency:cart.currency:'code' }}</dd></div><div><dt>Tax ({{ cart.tax_rate }}%)</dt><dd>{{ cart.tax | currency:cart.currency:'code' }}</dd></div><div class="payment-summary-total"><dt>Total</dt><dd>{{ cart.total | currency:cart.currency:'code' }}</dd></div></dl>
  </aside></div>
} @else { <h1>{{ loading() ? 'Opening checkout…' : 'Checkout unavailable' }}</h1><p role="status">{{ error() || 'Getting your order ready.' }}</p>@if (!loading()) { <p>Return to your shop cart to open a new checkout.</p><button mButton class="secondary" (click)="load()">Try again</button> } }
<footer>Powered by MSHOPPA</footer></main>`,styleUrl:'./checkout.css'})
export class PaymentCheckout {
  api=inject(Api); checkout=signal<Checkout|null>(null); loading=signal(true); busy=signal(false); error=signal('');
  failedImages=signal<Set<string>>(new Set());
  imageUrl(path:string,storeUrl:string) { if(!path || this.failedImages().has(path)) return ''; try { return new URL(path,storeUrl).href; } catch { return ''; } }
  imageFailed(path:string) { this.failedImages.update(paths=>new Set([...paths,path])); }
  token=new URLSearchParams(location.search).get('checkout') || '';
  form={name:'',email:'',phone:'',address:'',provider:''};
  constructor() { void this.load(); }
  async load() {
    if(this.busy()) return;
    this.loading.set(true); this.error.set('');
    try { const cart=await this.api.get<Checkout>(`checkout/?token=${encodeURIComponent(this.token)}`); if(cart.order) { location.replace(cart.order.payment_url || cart.return_url); return; } this.failedImages.set(new Set()); this.checkout.set(cart); if(!cart.methods.includes(this.form.provider)) this.form.provider=cart.methods[0] || ''; }
    catch(e) { this.error.set(errorMessage(e)); }
    finally { this.loading.set(false); }
  }
  async placeOrder() {
    const cart=this.checkout(); if(!cart || this.busy()) return;
    this.busy.set(true); this.error.set('');
    try { const order=await this.api.send<CheckoutOrder>('POST','checkout/',{token:this.token,details:{...this.form,quote_token:cart.quote_token}}); location.assign(order.payment_url || order.return_url); }
    catch(e) { this.error.set(errorMessage(e)); this.busy.set(false); }
  }
}
