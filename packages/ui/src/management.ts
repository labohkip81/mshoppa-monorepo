import { Component, DestroyRef, ElementRef, effect, inject, signal, untracked, viewChild } from '@angular/core';
import { DatePipe, TitleCasePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Api, Business, Page, errorMessage } from '@mshoppa/api';
import { Button, Icon } from './index';
import { StoreSelect } from './merchant';
import { Workspace } from './session';
import { PaymentWorkspace } from './payment-workspace';

type Section = 'orders' | 'businesses' | 'payments' | 'customers' | 'staff' | 'promotions';
interface OrderLine { id:number; product_name:string; variant_name:string; quantity:number; unit_price:string; line_total:string }
interface Order { id:string; customer_name:string; email:string; phone:string; address:string; currency:string; subtotal:string; tax:string; total:string; provider:string; status:string; created_at:string; fulfillment_status:string; staff_notes:string; tracking_reference:string; lines:OrderLine[] }
interface Payment { payment_backend:string; payment_review_required:boolean; id:string; customer_name:string; email:string; provider:string; status:string; total:string; currency:string; session_id:string; created_at:string }
interface Customer { email:string; order_count:number; paid_total:string; last_order:string }
interface Domain { id:number; hostname:string; verified:boolean; is_primary:boolean }
interface Staff { id:number; user_id:number; email:string; name:string; role:string }
interface Promotion { id:string; product_name:string; product_status:string; label:string; price:string; offer_price:string|null }

@Component({ standalone:true, imports:[FormsModule, RouterLink, DatePipe, TitleCasePipe, Button, Icon, StoreSelect, PaymentWorkspace], templateUrl:'./management.html', styleUrl:'./management.css' })
export class ManagementPage {
  api = inject(Api); workspace = inject(Workspace); route = inject(ActivatedRoute); destroyRef = inject(DestroyRef);
  section = signal<Section>('orders'); error = signal(''); message = signal(''); loading = signal(true); busy = signal(false);
  ready = signal(false); page = 1; count = signal(0); hasNext = signal(false); query = ''; status = ''; provider = ''; activeOffers = false;
  orders = signal<Order[]>([]); payments = signal<Payment[]>([]); customers = signal<Customer[]>([]); domains = signal<Domain[]>([]); staff = signal<Staff[]>([]); promotions = signal<Promotion[]>([]);
  showPaymentTransactions=signal(true);
  orderDialog=viewChild<ElementRef<HTMLDialogElement>>('orderDialog');
  selectedOrder = signal<Order|null>(null); customerOrders = signal<Order[]>([]); customerEmail = signal(''); historyNext = signal(false); historyPage = 1;
  fulfillment = { fulfillment_status:'unfulfilled', staff_notes:'', tracking_reference:'' };
  businessName = ''; hostname = ''; staffEmail = ''; staffRole = 'support'; staffRoles:Record<number,string> = {}; offers:Record<string,string> = {};
  confirmation = signal<{label:string; run:()=>Promise<void>}|null>(null);
  private generation = 0; private historyGeneration = 0;
  descriptions:Record<Section,string> = {
    orders:'Review incoming orders and keep fulfillment up to date.',
    businesses:'Manage your stores and their website addresses.',
    payments:'Configure payments, review transactions and manage your wallet.',
    customers:'Customers and purchase history from your store’s checkouts.',
    staff:'Manage who can access this store and what they can do.',
    promotions:'Set offer prices for products and their variants.',
  };
  constructor() {
    effect(()=>{ const dialog=this.orderDialog()?.nativeElement; const order=this.selectedOrder(); if(!dialog) return; if(order && !dialog.open) dialog.showModal(); else if(!order && dialog.open) dialog.close(); });
    this.route.data.pipe(takeUntilDestroyed()).subscribe(data => { this.section.set(data['section']); });
    effect(() => {
      const section = this.section(), business = this.workspace.selected(), ready = this.ready();
      if (!ready) return;
      untracked(() => { this.reset(); this.businessName = business?.name || ''; void this.load(section, business?.id); });
    });
    this.destroyRef.onDestroy(() => { this.generation++; this.historyGeneration++; });
    void this.workspace.load().then(() => this.ready.set(true)).catch(e => { this.error.set(errorMessage(e)); this.loading.set(false); });
  }
  reset() { this.page = 1; this.query = ''; this.status = ''; this.provider = ''; this.activeOffers = false; this.message.set(''); this.error.set(''); this.selectedOrder.set(null); this.customerEmail.set(''); this.customerOrders.set([]); this.historyGeneration++; this.confirmation.set(null); this.staffEmail = ''; this.staffRole = 'support'; this.hostname = ''; }
  canManage() { const b = this.workspace.selected(); return !!b && ['owner','manager'].includes(b.role) && !b.suspended; }
  canFulfill() { const b = this.workspace.selected(); return !!b && ['owner','manager','fulfillment'].includes(b.role) && !b.suspended; }
  canStaff() { const b = this.workspace.selected(); return b?.role === 'owner' && !b.suspended; }
  allowed() { const role = this.workspace.selected()?.role; return this.section() === 'staff' ? role === 'owner' : this.section() === 'payments' ? ['owner','manager'].includes(role || '') : true; }
  endpoint(section = this.section(), id = this.workspace.selected()!.id) { return `businesses/${id}/${section === 'businesses' ? 'domains' : section}/`; }
  async load(section = this.section(), id = this.workspace.selected()?.id) {
    const generation = ++this.generation;
    this.loading.set(true); this.error.set(''); this.selectedOrder.set(null);
    this.orders.set([]); this.payments.set([]); this.customers.set([]); this.domains.set([]); this.staff.set([]); this.promotions.set([]);
    if (!id || !this.allowed()) { this.loading.set(false); return; }
    const params = new URLSearchParams({ page:String(this.page) });
    if (this.query) params.set('q', this.query);
    if (this.status) params.set('status', this.status);
    if (this.provider) params.set('provider', this.provider);
    if (this.activeOffers) params.set('active', 'true');
    try {
      const result = await this.api.get<Page<never>>(`${this.endpoint(section,id)}?${params}`);
      if (generation !== this.generation) return;
      this.count.set(result.count); this.hasNext.set(!!result.next);
      switch (section) {
        case 'orders': this.orders.set(result.results); break;
        case 'payments': this.payments.set(result.results); break;
        case 'customers': this.customers.set(result.results); break;
        case 'businesses': this.domains.set(result.results); break;
        case 'staff': this.staff.set(result.results); this.staffRoles = Object.fromEntries(this.staff().map(s=>[s.id,s.role])); break;
        case 'promotions': this.promotions.set(result.results); this.offers = Object.fromEntries(this.promotions().map(p=>[p.id,p.offer_price ?? ''])); break;
      }
    } catch(e) { if (generation === this.generation) this.error.set(errorMessage(e)); }
    finally { if (generation === this.generation) this.loading.set(false); }
  }
  search() { this.page = 1; this.message.set(''); void this.load(); }
  paginate(delta:number) { this.page += delta; void this.load(); }
  async mutate(action:()=>Promise<unknown>, success:string) {
    if (this.busy()) return;
    const id = this.workspace.selected()?.id, section = this.section();
    this.busy.set(true); this.error.set(''); this.message.set('');
    try { await action(); if (this.workspace.selected()?.id === id && this.section() === section) this.message.set(success); }
    catch(e) { if (this.workspace.selected()?.id === id && this.section() === section) this.error.set(errorMessage(e)); }
    finally { this.busy.set(false); }
  }
  chooseBusiness(id:string) { if (!this.busy()) this.workspace.choose(id); }
  async rename() { const id = this.workspace.selected()!.id; await this.mutate(async()=>{ await this.api.send('PATCH',`businesses/${id}/`,{name:this.businessName}); await this.workspace.load(); },'Business name updated.'); }
  async addDomain() { const endpoint = this.endpoint(); await this.mutate(async()=>{ await this.api.send('POST',endpoint,{hostname:this.hostname}); this.hostname = ''; await this.workspace.load(); },'Domain added.'); }
  async primary(domain:Domain) { const endpoint = this.endpoint(); await this.mutate(async()=>{ await this.api.send('PATCH',`${endpoint}${domain.id}/`,{is_primary:true}); await this.workspace.load(); },'Primary domain updated.'); }
  removeDomain(domain:Domain) { const endpoint = this.endpoint(); this.confirmation.set({label:`Remove ${domain.hostname}? This address will stop opening this store.`,run:async()=>{await this.api.send('DELETE',`${endpoint}${domain.id}/`); await this.workspace.load();}}); }
  async addStaff() { const endpoint = this.endpoint(); await this.mutate(async()=>{ await this.api.send('POST',endpoint,{email:this.staffEmail,role:this.staffRole}); this.staffEmail=''; this.page=1; await this.load(); },'Staff member added.'); }
  updateStaff(member:Staff) { const endpoint = this.endpoint(), role = this.staffRoles[member.id]; this.confirmation.set({label:`Change ${member.email} to ${role}? Their store permissions will change immediately.`,run:async()=>{await this.api.send('PATCH',`${endpoint}${member.id}/`,{role}); await this.load();}}); }
  removeStaff(member:Staff) { const endpoint = this.endpoint(); this.confirmation.set({label:`Remove ${member.email} from this store? Their store access will end immediately.`,run:async()=>{await this.api.send('DELETE',`${endpoint}${member.id}/`); this.page=1; await this.load();}}); }
  async confirm() { const action = this.confirmation(); if (action) await this.mutate(async()=>{ await action.run(); this.confirmation.set(null); },'Changes saved.'); }
  closeOrder() { if(!this.busy()) this.selectedOrder.set(null); }
  cancelOrder(event:Event) { if(this.busy()) event.preventDefault(); else this.selectedOrder.set(null); }
  openOrder(order:Order) { this.error.set(''); this.message.set(''); this.selectedOrder.set(order); this.fulfillment = {fulfillment_status:order.fulfillment_status,staff_notes:order.staff_notes,tracking_reference:order.tracking_reference}; }
  async saveOrder() { const order = this.selectedOrder()!, endpoint = this.endpoint(); await this.mutate(async()=>{ const updated = await this.api.send<Order>('PATCH',`${endpoint}${order.id}/`,this.fulfillment); this.orders.update(rows=>rows.map(row=>row.id===updated.id ? updated : row)); this.openOrder(updated); },'Order updated.'); }
  statusOptions(order:Order) { const statuses = ['unfulfilled','processing','shipped','delivered']; return order.status === 'paid' ? statuses.slice(statuses.indexOf(order.fulfillment_status)) : ['unfulfilled']; }
  async history(email:string, more=false) {
    const id=this.workspace.selected()!.id, generation=++this.historyGeneration;
    if (!more) { this.customerEmail.set(email); this.customerOrders.set([]); this.historyPage=1; }
    this.busy.set(true); this.error.set('');
    try { const data=await this.api.get<Page<Order>>(`businesses/${id}/orders/?email=${encodeURIComponent(email)}&page=${this.historyPage}`); if (generation!==this.historyGeneration) return; this.customerOrders.update(rows=>more?[...rows,...data.results]:data.results); this.historyNext.set(!!data.next); this.historyPage++; }
    catch(e) { if (generation===this.historyGeneration) this.error.set(errorMessage(e)); }
    finally { this.busy.set(false); }
  }
  async saveOffer(promotion:Promotion) { const endpoint=this.endpoint(), value=this.offers[promotion.id]; await this.mutate(async()=>{ await this.api.send('PATCH',`${endpoint}${promotion.id}/`,{offer_price:value === '' ? null : value}); await this.load(); },'Offer price saved.'); }
  money(value:string, currency=this.workspace.selected()?.currency || 'KES') { return `${currency} ${Number(value).toLocaleString(undefined,{minimumFractionDigits:['UGX','RWF'].includes(currency)?0:2,maximumFractionDigits:2})}`; }
  shortId(id:string) { return id.slice(0,8).toUpperCase(); }
}
