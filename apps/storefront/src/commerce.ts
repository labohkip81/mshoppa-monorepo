import { Component, ElementRef, Injectable, OnDestroy, computed, effect, inject, signal, viewChild } from '@angular/core';
import { CurrencyPipe, DatePipe } from '@angular/common';
import { Api, Product, StoreSettings, errorMessage } from '@mshoppa/api';
import { Icon } from '@mshoppa/ui';

interface StoreContext { id:string; name:string; currency:string; settings:StoreSettings; preview:boolean }
interface CartLine { variant_id:string; quantity:number; name:string; label:string; image:string }
interface CartVariant { id:string; label:string; price:string; stock:number }
interface QuoteLine { variants:CartVariant[]; variant_id:string; quantity:number; product_name:string; variant_name:string; unit_price:string; line_total:string; stock:number; image_url:string }
interface Quote { lines:QuoteLine[]; subtotal:string; tax:string; tax_rate:string; total:string; currency:string; methods:string[]; quote_token:string }
interface Order { created_at:string; fulfillment_status:string; tracking_reference:string; test_mode:boolean; payment_review_required:boolean; id:string; token:string; status:string; provider:string; currency:string; subtotal:string; tax:string; total:string; payment_url:string; lines:QuoteLine[] }

@Injectable({providedIn:'root'})
export class CartService {
  api = inject(Api); store = signal<StoreContext|null>(null); items = signal<CartLine[]>([]); open = signal(false);
  count = computed(() => this.items().reduce((total, item) => total + item.quantity, 0));
  quote = signal<Quote|null>(null); busy = signal(false); checkoutBusy = signal(false); error = signal(''); private sequence = 0;
  init(store:StoreContext) {
    this.store.set(store);
    if (store.preview) { this.items.set([]); return; }
    try {
      const saved:unknown = JSON.parse(localStorage.getItem(this.key()) || '[]');
      const unique = new Set<string>();
      this.items.set(Array.isArray(saved) ? saved.filter((row:any) => row && typeof row.variant_id === 'string' && /^[0-9a-f-]{36}$/i.test(row.variant_id) && Number.isInteger(row.quantity) && row.quantity > 0 && row.quantity <= 99 && typeof row.name === 'string' && typeof row.label === 'string' && !unique.has(row.variant_id) && !!unique.add(row.variant_id)).slice(0,50).map((row:any) => ({variant_id:row.variant_id,quantity:row.quantity,name:row.name.slice(0,180),label:row.label.slice(0,120),image:''})) : []);
    } catch { this.items.set([]); }
  }
  private key() { return `mshoppa.cart.v1.${this.store()?.id}`; }
  private persist() { try { localStorage.setItem(this.key(), JSON.stringify(this.items().map(({image,...row}) => row))); } catch { this.error.set('Your browser could not save the cart. Keep this tab open.'); } }
  add(product:Product, variant?:Product['variants'][number]) {
    if (this.store()?.preview || !variant || !variant.stock || product.status !== 'published') return;
    const existing = this.items().find(item => item.variant_id === variant.id);
    if ((existing?.quantity || 0) >= Math.min(99, variant.stock)) { this.error.set('You have reached the available quantity.'); this.open.set(true); return; }
    if (!existing && this.items().length >= 50) { this.error.set('Your cart can contain up to 50 variants.'); this.open.set(true); return; }
    this.items.update(items => existing ? items.map(item => item.variant_id === variant.id ? {...item,quantity:item.quantity+1} : item) : [...items,{variant_id:variant.id,quantity:1,name:product.name,label:variant.label || 'Default',image:product.images[0]?.url || ''}]);
    this.persist(); this.open.set(true); void this.refresh();
  }
  quantity(id:string, value:number) { if (this.busy() || this.checkoutBusy()) return; this.items.update(items => value <= 0 ? items.filter(item => item.variant_id !== id) : items.map(item => item.variant_id === id ? {...item,quantity:Math.min(value,99)} : item)); this.persist(); void this.refresh(); }
  changeVariant(id:string, targetId:string):boolean {
    if (this.busy() || this.checkoutBusy()) return false;
    const item=this.items().find(row=>row.variant_id===id);
    const variant=this.quote()?.lines.find(row=>row.variant_id===id)?.variants.find(option=>option.id===targetId);
    if (!item || !variant || targetId===id) return false;
    const existing=this.items().find(row=>row.variant_id===targetId);
    const quantity=item.quantity+(existing?.quantity || 0);
    if (quantity>Math.min(99,variant.stock)) { this.error.set(`Only ${variant.stock} available for ${variant.label}. Reduce the quantity before changing variants.`); return false; }
    this.items.update(rows=>existing ? rows.filter(row=>row.variant_id!==id).map(row=>row.variant_id===targetId ? {...row,quantity} : row) : rows.map(row=>row.variant_id===id ? {...row,variant_id:targetId,label:variant.label} : row));
    this.persist(); void this.refresh(); return true;
  }
  payload() { return this.items().map(({variant_id,quantity}) => ({variant_id,quantity})); }
  async refresh() {
    const sequence = ++this.sequence;
    this.quote.set(null); this.error.set('');
    if (!this.items().length) { this.busy.set(false); return; }
    this.busy.set(true);
    try { const result = await this.api.send<Quote>('POST','cart/quote/',{items:this.payload()}); if (sequence === this.sequence) this.quote.set(result); }
    catch(e) { if (sequence === this.sequence) this.error.set(errorMessage(e)); }
    finally { if (sequence === this.sequence) this.busy.set(false); }
  }
  async checkout() {
    if (this.checkoutBusy() || !this.items().length || this.store()?.preview) return;
    this.checkoutBusy.set(true); this.error.set('');
    try { const result=await this.api.send<{payment_url:string}>('POST','checkout/handoff/',{items:this.payload()}); location.assign(result.payment_url); }
    catch(e) { this.error.set(errorMessage(e)); this.checkoutBusy.set(false); }
  }
  clear() { this.sequence++; this.items.set([]); this.quote.set(null); this.persist(); }
}

@Component({selector:'m-cart-controls',standalone:true,imports:[CurrencyPipe,Icon],templateUrl:'./cart.html'})
export class CartControls {
  cart = inject(CartService); drawer = viewChild<ElementRef<HTMLDialogElement>>('drawer');
  constructor() { effect(() => { const dialog = this.drawer()?.nativeElement; if (!dialog) return; if (this.cart.open() && !dialog.open) dialog.showModal(); else if (!this.cart.open() && dialog.open) dialog.close(); }); }
  show() { this.cart.open.set(true); void this.cart.refresh(); }
  lineFor(id:string) { return this.cart.quote()?.lines.find(line => line.variant_id === id); }
  switchVariant(id:string,event:Event) { const select=event.target as HTMLSelectElement; if(!this.cart.changeVariant(id,select.value)) select.value=id; }
  imageFor(id:string) { return this.lineFor(id)?.image_url || this.cart.items().find(item => item.variant_id === id)?.image || ''; }
}

@Component({selector:'m-store-checkout',standalone:true,imports:[CurrencyPipe,DatePipe,Icon],templateUrl:'./checkout.html'})
export class StoreCheckout implements OnDestroy {
  cart = inject(CartService); api = inject(Api); error = signal(''); busy = signal(false); order = signal<Order|null>(null); loadingOrder = signal(false); checking = signal(false); checkedAt = signal<Date|null>(null);
  orderToken = new URLSearchParams(location.search).get('order'); private timer?:ReturnType<typeof setTimeout>; private destroyed = false;
  constructor() { if (this.orderToken) void this.loadOrder(); else void this.cart.checkout(); }
  ngOnDestroy() { this.destroyed = true; clearTimeout(this.timer); }
  trackingSteps = ['Order placed','Payment confirmed','Preparing your order','Shipped','Delivered'];
  trackingIndex(order:Order) { return order.status !== 'paid' ? 0 : ({unfulfilled:1,processing:2,shipped:3,delivered:4} as Record<string,number>)[order.fulfillment_status] ?? 1; }
  trackingTitle(order:Order) { return order.payment_review_required ? 'Payment under review' : order.status === 'paid' ? ({unfulfilled:'Order confirmed',processing:'Preparing your order',shipped:'Your order is on its way',delivered:'Your order has arrived'} as Record<string,string>)[order.fulfillment_status] || 'Order confirmed' : order.status === 'pending' ? 'Awaiting payment' : order.status === 'failed' ? 'Payment unsuccessful' : 'Checkout expired'; }
  async loadOrder() {
    if (!this.orderToken || this.destroyed || this.checking()) return;
    clearTimeout(this.timer); this.checking.set(true);
    this.loadingOrder.set(!this.order()); this.error.set('');
    try {
      const order = await this.api.get<Order>(`orders/${encodeURIComponent(this.orderToken)}/`);
      if (this.destroyed) return;
      this.order.set(order); this.checkedAt.set(new Date());
      if (order.status === 'paid') {
        const key = `mshoppa.completed.${this.cart.store()?.id}`;
        try { if (localStorage.getItem(key) !== order.token) { this.cart.clear(); localStorage.setItem(key,order.token); } } catch { this.cart.clear(); }
      }
      if (order.status === 'pending' || (order.status === 'paid' && order.fulfillment_status !== 'delivered')) this.timer = setTimeout(() => void this.loadOrder(),order.status === 'pending' ? 3000 : 15000);
    } catch(e) { this.error.set(errorMessage(e)); }
    finally { this.loadingOrder.set(false); this.checking.set(false); }
  }
}
