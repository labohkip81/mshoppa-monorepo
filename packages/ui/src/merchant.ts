import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Api, errorMessage, StoreSettings, Page, Product } from '@mshoppa/api';
import { Button, Icon, SOCIAL_PROFILES } from './index';
import { Workspace } from './session';
import { RichTextEditor } from './rich-text';

@Component({ selector: 'm-store-select', standalone: true, imports: [FormsModule], template: `@if (workspace.businesses().length) { <label class="store-select"><span class="sr-only">Current business</span><select [ngModel]="workspace.selected()?.id" (ngModelChange)="workspace.choose($event)">@for (business of workspace.businesses(); track business.id) { <option [value]="business.id">{{ business.name }}</option> }</select></label> }` })
export class StoreSelect { workspace = inject(Workspace); }

@Component({ standalone: true, imports: [RouterLink, Button, Icon, StoreSelect], template: `
  <div class="page-heading"><div><h1>Good to see you, {{ api.user()?.first_name || 'there' }}.</h1><p>A little clarity for your next big move.</p></div><m-store-select /></div>
  @if (error()) { <div class="notice error" role="alert">{{ error() }}</div> }
  @if (loading()) { <div class="loading-state" role="status">Opening your workspace…</div> }
  @else if (workspace.selected(); as business) {
    <section class="welcome-panel"><div><h2>Let’s make {{ business.name }}<br>a place people love.</h2><p>Your store is taking shape. Start with the essentials,<br class="desktop-only"> and make it feel like you.</p><a mButton routerLink="/products">Add your first products<m-icon name="arrow" /></a></div></section>
    <div class="overview-grid"><section class="panel"><div class="section-heading"><div><h2>A good place to begin</h2><p class="muted">Small steps. Something wonderful.</p></div><span class="badge">Getting started</span></div><a class="checklist-row" routerLink="/applications"><span class="step-icon done"><m-icon name="check" /></span><div><strong>Business approved</strong><p>You’re part of the MSHOPPA community.</p></div><m-icon name="arrow" /></a><a class="checklist-row" routerLink="/products"><span class="step-icon">2</span><div><strong>Bring your products to life</strong><p>Add the essentials to your first collection.</p></div><m-icon name="arrow" /></a><a class="checklist-row" routerLink="/settings"><span class="step-icon">3</span><div><strong>Make yourself at home</strong><p>Give your storefront a voice and a visual style.</p></div><m-icon name="arrow" /></a><div class="checklist-row future"><span class="step-icon">4</span><div><strong>Get ready to take your first order</strong><p>Checkout, delivery and publishing arrive in the next phase.</p></div></div></section>
    <section class="panel store-summary"><div class="section-heading"><h2>Your store at a glance</h2><m-icon name="globe" /></div><div class="summary-brand">{{ business.name.slice(0,1) }}</div><h3>{{ business.name }}</h3><p class="muted">{{ business.domains[0]?.hostname || business.slug + '.localhost' }}</p><dl><div><dt>Store status</dt><dd><span class="badge">{{ business.suspended ? 'Suspended' : business.published ? 'Online' : 'Offline' }}</span></dd></div><div><dt>Setup</dt><dd>{{ business.provisioning_status }}</dd></div><div><dt>Currency</dt><dd>{{ business.currency }}</dd></div><div><dt>Your role</dt><dd>{{ business.role }}</dd></div></dl><a class="text-link" routerLink="/settings">Manage store settings<m-icon name="arrow" /></a></section></div>
  } @else { <section class="panel empty-state"><div class="empty-icon"><m-icon name="bag" /></div><h2>Your business belongs here.</h2><p>Tell us a little about it. We’ll help you take the next step.</p><a mButton routerLink="/applications">Start your application<m-icon name="arrow" /></a></section> }
` })
export class OverviewPage {
  api = inject(Api); workspace = inject(Workspace); loading = signal(true); error = signal('');
  constructor() { this.workspace.load().catch(e => this.error.set(errorMessage(e))).finally(() => this.loading.set(false)); }
}


@Component({ standalone: true, imports: [FormsModule, RouterLink, Button, Icon, RichTextEditor], template: `
  <div class="page-heading"><div><h1>Store settings</h1><p>The small details that make your business unmistakable.</p></div>@if (workspace.businesses().length > 1) { <label><span class="sr-only">Current business</span><select [ngModel]="workspace.selected()?.id" (ngModelChange)="switchStore($event)">@for (business of workspace.businesses(); track business.id) { <option [value]="business.id">{{ business.name }}</option> }</select></label> }</div>
  @if (error()) { <div class="notice error" role="alert">{{ error() }}</div> } @if (message()) { <div class="notice success" role="status">{{ message() }}</div> }
  @if (loading()) { <div class="loading-state" role="status">Loading your store…</div> }
  @else if (workspace.selected(); as business) {
    <section class="panel website-status-panel"><div><h2>Website visibility</h2><p class="muted">{{ form.published ? 'Your website is online. Visitors can browse published products.' : 'Your website is offline. Only staff with a private preview link can view it.' }}</p><p class="field-hint">Approved businesses go online automatically. Turn this off whenever you need a pause.</p></div><label class="website-switch"><input type="checkbox" role="switch" [checked]="form.published" (change)="setOnline($event)" [disabled]="busy() || !canWrite()" aria-label="Website online"><span aria-hidden="true"></span><strong>{{ form.published ? 'Online' : 'Offline' }}</strong></label></section>
    <section class="panel form-panel settings-section" id="store-branding"><div class="section-heading"><div><h2>Logo &amp; cover image</h2><p class="muted">Make your storefront yours. Your cover appears behind your shop profile.</p></div></div>
      <div class="branding-preview" [style.--brand-tone]="tones[form.surface_tone]"><div class="branding-cover">@if (form.cover_url) { <img [src]="form.cover_url" alt="Store cover preview"> }</div><div class="branding-profile"><div class="branding-logo">@if (form.logo_url) { <img [src]="form.logo_url" [alt]="business.name + ' logo'"> } @else { <span>{{ business.name.slice(0,1) }}</span> }</div><strong>{{ business.name }}</strong></div></div>
      <div class="branding-upload-grid"><div><h3>Store logo</h3><p class="field-hint">Use a square image. It appears in your header, profile and footer.</p><label>Upload logo<input type="file" accept="image/jpeg,image/png,image/webp" (change)="uploadBrandImage($event, 'logo')" [disabled]="busy() || !canWrite()"></label>@if (form.logo_url) { <button type="button" mButton class="secondary compact" (click)="removeBrandImage('logo')" [disabled]="busy() || !canWrite()">Remove logo</button> }</div><div><h3>Cover image</h3><p class="field-hint">Use a wide image, ideally 1800 × 500 px. A gradient appears when empty.</p><label>Upload cover image<input type="file" accept="image/jpeg,image/png,image/webp" (change)="uploadBrandImage($event, 'cover')" [disabled]="busy() || !canWrite()"></label>@if (form.cover_url) { <button type="button" mButton class="secondary compact" (click)="removeBrandImage('cover')" [disabled]="busy() || !canWrite()">Remove cover</button> }</div></div><p class="field-hint">JPEG, PNG or WebP, up to 5 MB. Uploads and removal save immediately.</p>
    </section>
    <nav class="settings-shortcuts" aria-label="Store settings sections"><a href="#store-branding"><m-icon name="store" />Logo &amp; cover</a><a href="#store-social"><m-icon name="globe" />Social media</a><a href="#store-policies"><m-icon name="file" />Terms &amp; policies</a></nav>
    <section class="panel form-panel"><div class="section-heading"><div><h2>Checkout &amp; payments</h2><p class="muted">Choose the methods offered at checkout. Provider configuration is shown under Payments.</p></div></div><form (ngSubmit)="save()"><label>Tax rate (%)<input name="tax_rate" [(ngModel)]="form.tax_rate" type="number" min="0" max="100" step="0.01" required></label><p class="field-hint">Added to tax-exclusive product prices at checkout. Defaults to 0% for testing; configure the appropriate rate before testing your totals.</p><label class="variant-toggle"><input type="checkbox" name="stripe_enabled" [(ngModel)]="form.stripe_enabled"><span>Stripe — test card payments</span></label><label class="variant-toggle"><input type="checkbox" name="mpesa_enabled" [(ngModel)]="form.mpesa_enabled"><span>M-Pesa — via Venty</span></label><button mButton [disabled]="busy() || !canWrite()">Save checkout settings</button></form></section>
    <div class="settings-grid"><section class="panel form-panel"><div class="section-heading"><div><h2>Store identity</h2><p class="muted">A warm welcome, in your own words.</p></div><m-icon name="settings" /></div><form (ngSubmit)="save()"><label>Homepage headline<input name="headline" [(ngModel)]="form.headline" maxlength="160" required></label><m-rich-text label="Your introduction" name="description" [(ngModel)]="form.description" [maxLength]="500" placeholder="A short introduction to your store." [readOnly]="busy() || !canWrite()" /><label>Customer contact email<input type="email" name="contact_email" [(ngModel)]="form.contact_email" placeholder="hello@yourbusiness.com"></label><div class="form-actions"><span class="muted">Saved changes appear on your website when it is online.</span><button mButton [disabled]="busy() || !canWrite()">{{ busy() ? 'Saving…' : 'Save changes' }}</button></div></form></section>
    <section class="panel theme-panel"><div class="section-heading"><div><h2>Natural 01</h2><p class="muted">Quietly distinctive. Effortlessly yours.</p></div><span class="badge">Storefront theme</span></div><div class="theme-preview" [style.--tone]="tones[form.surface_tone]"><span>{{ business.name }}</span><h3>{{ form.headline }}</h3><div class="theme-blocks"><i></i><i></i></div><span class="preview-pill">Explore the collection</span></div><label class="tone-label">Material tone<select name="surface_tone" [(ngModel)]="form.surface_tone"><option value="taupe">Warm taupe</option><option value="sky">Muted sky</option><option value="mauve">Dusty mauve</option><option value="olive">Olive</option><option value="cream">Warm cream</option></select></label><p class="field-hint">Preview only. Save changes to keep your selection.</p></section></div>
    <section class="panel form-panel"><div class="section-heading"><div><h2>Featured product</h2><p class="muted">Choose the first product in your storefront’s featured sort order.</p></div></div><form (ngSubmit)="save()"><label>Homepage featured product<select name="featured_product" [(ngModel)]="form.featured_product" [disabled]="busy() || !canWrite()"><option [ngValue]="null">Automatic — newest published product</option>@for (product of featuredOptions(); track product.id) { <option [ngValue]="product.id">{{ product.name }}{{ product.status === 'draft' ? ' (draft — automatic fallback)' : '' }}</option> }</select></label>@if (moreFeatured()) { <button type="button" mButton class="secondary compact" (click)="loadMoreFeatured()" [disabled]="loadingFeatured()">{{ loadingFeatured() ? 'Loading…' : 'Load more products' }}</button> }<p class="field-hint">Only published products can be featured. If your selection is unavailable, the newest published product is shown. With no published products, your shop profile and cover are still shown.</p><div class="form-actions"><span class="muted">Choose Automatic to clear your selection.</span><button mButton [disabled]="busy() || !canWrite()">{{ busy() ? 'Saving…' : 'Save changes' }}</button></div></form></section>

    <section class="panel form-panel"><div class="section-heading"><div><h2>Footer &amp; contact details</h2><p class="muted">Only filled-in details appear on your website. Your introduction is the footer description.</p></div></div><form (ngSubmit)="save()"><label>Store phone<input type="tel" name="contact_phone" [(ngModel)]="form.contact_phone" placeholder="+254700000000" maxlength="30"></label><p class="field-hint">When blank, the phone from your approved application is used.</p><label>Store address<textarea name="contact_address" [(ngModel)]="form.contact_address" maxlength="300" rows="3"></textarea></label><label>WhatsApp number<input type="tel" name="whatsapp_number" [(ngModel)]="form.whatsapp_number" placeholder="254700000000" maxlength="30"></label><p class="field-hint">Include the country code. The top-bar WhatsApp link uses this number, or your store phone when blank. The floating button appears only when this number is set.</p><div class="form-actions"><span class="muted">Contact email and description are edited under Store identity.</span><button mButton [disabled]="busy() || !canWrite()">{{ busy() ? 'Saving…' : 'Save changes' }}</button></div></form></section>
    <section class="panel form-panel settings-section" id="store-social" aria-labelledby="social-heading"><div class="section-heading"><div><h2 id="social-heading">Social media</h2><p class="muted">Add your profile links. Matching icons appear on your shop profile and in the footer.</p></div></div><form (ngSubmit)="save('social')"><div class="social-settings-grid">@for (social of socialFields; track social.key) { <label class="social-profile-field"><span><m-icon [name]="social.icon" />{{ social.label }}</span><input type="url" [name]="social.key" [(ngModel)]="form[social.key]" [placeholder]="social.placeholder" maxlength="200" [disabled]="busy() || !canWrite()"></label> }</div><p class="field-hint">Leave a link empty to hide its icon. No icon upload is needed.</p><div class="form-actions"><span class="muted" role="status">{{ savedSection() === 'social' ? 'Social links saved.' : 'Only these social links are saved.' }}</span><button mButton [disabled]="busy() || !canWrite()">{{ busy() ? 'Saving…' : 'Save social links' }}</button></div></form></section>
    <section class="panel form-panel settings-section" id="store-policies" aria-labelledby="policies-heading"><div class="section-heading"><div><h2 id="policies-heading">Terms &amp; policies</h2><p class="muted">Write the policies customers can read from your storefront footer.</p></div></div><form (ngSubmit)="save('policies')"><m-rich-text label="Terms and conditions" name="terms_conditions" [(ngModel)]="form.terms_conditions" [maxLength]="20000" [minHeight]="200" [readOnly]="busy() || !canWrite()" /><m-rich-text label="Privacy policy" name="privacy_policy" [(ngModel)]="form.privacy_policy" [maxLength]="20000" [minHeight]="200" [readOnly]="busy() || !canWrite()" /><m-rich-text label="Return / refund policy" name="return_refund_policy" [(ngModel)]="form.return_refund_policy" [maxLength]="20000" [minHeight]="200" [readOnly]="busy() || !canWrite()" /><p class="field-hint">Empty policies stay hidden. Use the toolbar to add headings, lists, formatting and links. Check that each policy reflects how your business operates.</p><div class="form-actions"><span class="muted" role="status">{{ savedSection() === 'policies' ? 'Store policies saved.' : 'Only these policy texts are saved.' }}</span><button mButton [disabled]="busy() || !canWrite()">{{ busy() ? 'Saving…' : 'Save policies' }}</button></div></form></section>
    <section class="panel"><div class="section-heading"><div><h2>Your store address</h2><p class="muted">A place to call your own.</p></div><button mButton class="secondary compact" (click)="preview()" [disabled]="busy()">Private preview <m-icon name="arrow" /></button></div>@for (domain of business.domains; track domain.hostname) { <div class="domain-row"><strong>{{ domain.hostname }}</strong><span class="badge">{{ domain.verified ? 'Verified locally' : 'Not verified' }}</span></div> }<p class="panel-footnote">Your local storefront opens at http://&lt;store-address&gt;:4203. Custom domains and production hosting are not connected yet.</p></section>
  } @else { <section class="panel empty-state"><h2>Your store is still ahead of you.</h2><p>Once your business is approved, its settings will appear here.</p><a mButton routerLink="/applications">View applications</a></section> }
` })
export class SettingsPage {
  api = inject(Api); workspace = inject(Workspace); loading = signal(true); busy = signal(false); error = signal(''); message = signal('');
  form: StoreSettings = { headline:'',description:'',contact_email:'',theme_id:'natural-01',surface_tone:'taupe',logo_url:'',cover_url:'' };
  socialFields = SOCIAL_PROFILES;
  savedSection = signal<'social'|'policies'|null>(null);
  async uploadBrandImage(event: Event, kind: 'logo'|'cover') {
    const input = event.target as HTMLInputElement, file = input.files?.[0];
    if (!file || this.busy() || !this.canWrite()) return;
    if (file.size > 5 * 1024 * 1024) { this.error.set('Image must be 5 MB or smaller.'); input.value = ''; return; }
    const id = this.workspace.selected()!.id;
    this.busy.set(true); this.error.set(''); this.message.set('');
    try {
      const body = new FormData(); body.append('image', file);
      const saved = await this.api.send<StoreSettings>('POST', `businesses/${id}/${kind}/`, body);
      if (this.workspace.selected()?.id === id) {
        const key = kind === 'logo' ? 'logo_url' : 'cover_url';
        this.form = {...this.form, [key]:saved[key]}; this.message.set(`Store ${kind} uploaded.`);
      }
    } catch(e) { this.error.set(errorMessage(e)); } finally { this.busy.set(false); input.value = ''; }
  }
  async removeBrandImage(kind: 'logo'|'cover') {
    if (this.busy() || !this.canWrite()) return;
    const id = this.workspace.selected()!.id;
    this.busy.set(true); this.error.set(''); this.message.set('');
    try {
      await this.api.send('DELETE', `businesses/${id}/${kind}/`);
      if (this.workspace.selected()?.id === id) {
        this.form = {...this.form, [kind === 'logo' ? 'logo_url' : 'cover_url']:''}; this.message.set(`Store ${kind} removed.`);
      }
    } catch(e) { this.error.set(errorMessage(e)); } finally { this.busy.set(false); }
  }
  tones: Record<string,string> = {taupe:'#d1b0a4',sky:'#879aab',mauve:'#a57e75',olive:'#9e8949',cream:'#e0dacf'};
  featuredOptions = signal<Product[]>([]); moreFeatured = signal(false); loadingFeatured = signal(false); private featuredPage = 1; private settingsLoad = 0;
  async loadMoreFeatured() {
    const businessId = this.workspace.selected()?.id, generation = this.settingsLoad;
    if (!businessId || this.loadingFeatured()) return;
    this.loadingFeatured.set(true);
    try {
      const result = await this.api.get<Page<Product>>(`businesses/${businessId}/products/?status=published&page=${this.featuredPage}`);
      if (generation !== this.settingsLoad) return;
      this.featuredOptions.update(current => [...new Map([...current,...result.results].map(product => [product.id,product])).values()]);
      this.moreFeatured.set(!!result.next); this.featuredPage += 1;
    } catch(e) { if (generation === this.settingsLoad) this.error.set(errorMessage(e)); } finally { if (generation === this.settingsLoad) this.loadingFeatured.set(false); }
  }
  async setOnline(event: Event) {
    const control = event.target as HTMLInputElement, published = control.checked;
    control.checked = !!this.form.published;
    this.busy.set(true); this.error.set(''); this.message.set('');
    try {
      const saved = await this.api.send<StoreSettings>('PATCH', `businesses/${this.workspace.selected()!.id}/settings/`, {published});
      this.form = {...this.form, published:saved.published};
      control.checked = !!saved.published;
      this.workspace.selected.update(business => business ? {...business, published:!!saved.published} : business);
      this.message.set(saved.published ? 'Your website is now online.' : 'Your website is now offline. You can continue editing it here.');
    } catch(e) { this.error.set(errorMessage(e)); }
    finally { this.busy.set(false); }
  }
  async preview() { this.busy.set(true); this.error.set(''); try { const result = await this.api.send<{url:string}>('POST', `businesses/${this.workspace.selected()!.id}/preview-link/`); location.assign(result.url); } catch(e) { this.error.set(errorMessage(e)); } finally { this.busy.set(false); } }
  constructor() { void this.init(); }
  canWrite() { return ['owner','manager'].includes(this.workspace.selected()?.role || '') && !this.workspace.selected()?.suspended; }
  async init() { try { await this.workspace.load(); await this.load(); } catch(e) { this.error.set(errorMessage(e)); this.loading.set(false); } }
  switchStore(id: string) { if (this.busy()) return; this.workspace.choose(id); this.message.set(''); void this.load(); }
  async load() {
    const generation = ++this.settingsLoad, businessId = this.workspace.selected()?.id;
    this.loading.set(true); this.error.set(''); this.savedSection.set(null); this.featuredOptions.set([]); this.moreFeatured.set(false); this.loadingFeatured.set(false); this.featuredPage = 1;
    try {
      if (!businessId) return;
      const settings = await this.api.get<StoreSettings>(`businesses/${businessId}/settings/`);
      if (generation !== this.settingsLoad) return;
      this.form = {...settings, featured_product:settings.featured_product ?? null};
      if (settings.featured_product) {
        const product = await this.api.get<Product>(`businesses/${businessId}/products/${settings.featured_product}/`);
        if (generation !== this.settingsLoad) return;
        this.featuredOptions.set([product]);
      }
      await this.loadMoreFeatured();
    } catch(e) { if (generation === this.settingsLoad) this.error.set(errorMessage(e)); } finally { if (generation === this.settingsLoad) this.loading.set(false); }
  }
  async save(section?: 'social'|'policies') {
    this.busy.set(true); this.error.set(''); this.message.set(''); this.savedSection.set(null);
    const fields: readonly (keyof StoreSettings)[] = section === 'social' ? this.socialFields.map(social => social.key) : ['terms_conditions','privacy_policy','return_refund_policy'];
    const changes = section ? Object.fromEntries(fields.map(key => [key, this.form[key] ?? ''])) : this.form;
    try {
      const saved = await this.api.send<StoreSettings>('PATCH', `businesses/${this.workspace.selected()!.id}/settings/`, changes);
      this.form = section ? {...this.form,...Object.fromEntries(fields.map(key => [key, saved[key]]))} : saved;
      this.savedSection.set(section ?? null); this.message.set(section === 'social' ? 'Your social links have been saved.' : section === 'policies' ? 'Your store policies have been saved.' : 'Your store settings have been saved.');
    } catch(e) { this.error.set(errorMessage(e)); } finally { this.busy.set(false); }
  }
}
