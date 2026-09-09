import { Component, inject, signal } from '@angular/core';
import { DatePipe, TitleCasePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Api, Application, errorMessage, Page } from '@mshoppa/api';
import { Button, Icon, PORTAL } from './index';

@Component({ standalone: true, imports: [FormsModule, DatePipe, TitleCasePipe, Button, Icon], template: `
  <div class="page-heading"><div><h1>{{ platform ? 'Business applications' : 'Your applications' }}</h1><p>{{ platform ? 'Meet the businesses ready for their next chapter.' : 'Start a new business, or pick up where you left off.' }}</p></div>@if (!platform) { <button mButton (click)="newApplication()"><m-icon name="plus" />New application</button> }</div>
  @if (error()) { <div class="notice error" role="alert">{{ error() }}</div> }
  @if (message()) { <div class="notice success" role="status">{{ message() }}</div> }
  @if (platform) { <div class="filter-bar"><div class="tabs">@for (tab of tabs; track tab.value) { <button [class.selected]="filter === tab.value" (click)="setFilter(tab.value)">{{ tab.label }}</button> }</div><button mButton class="secondary compact" (click)="load()" [disabled]="busy()">Refresh</button></div> }
  @if (editing()) {
    <section class="panel form-panel"><div class="section-heading"><div><h2>{{ editingId ? 'Update your application' : 'Tell us about your business' }}</h2><p class="muted">A few details to help us get you set up.</p></div><button class="icon-button" (click)="editing.set(false)" aria-label="Close application form"><m-icon name="close" /></button></div>
    <form (ngSubmit)="save()"><div class="form-grid"><label>Business name<input name="name" [(ngModel)]="form.name" required maxlength="120" placeholder="e.g. Everyday Studio"></label><label>Store address<div class="input-suffix"><input name="slug" [(ngModel)]="form.slug" required pattern="[a-z][a-z0-9-]{1,48}[a-z0-9]" placeholder="everyday-studio"><span>.localhost</span></div></label><label>Category<input name="category" [(ngModel)]="form.category" required maxlength="60" placeholder="e.g. Home & living"></label><label>Business phone<input name="phone" [(ngModel)]="form.phone" type="tel" required maxlength="30" placeholder="+254 700 000 000"></label><label>Country<select name="country" [(ngModel)]="form.country"><option value="KE">Kenya</option><option value="UG">Uganda</option><option value="TZ">Tanzania</option><option value="RW">Rwanda</option><option value="US">United States</option><option value="GB">United Kingdom</option><option value="ZA">South Africa</option><option value="NG">Nigeria</option><option value="GH">Ghana</option></select></label><label>Store currency<select name="currency" [(ngModel)]="form.currency">@for (currency of currencies; track currency) { <option [value]="currency">{{ currency }}</option> }</select></label></div><label>What makes your business yours?<textarea name="description" [(ngModel)]="form.description" rows="3" maxlength="2000" placeholder="Tell us a little about your products and your business."></textarea></label><div class="form-actions"><span class="muted">Save first. Submit when you’re ready.</span><button mButton [disabled]="busy()">{{ busy() ? 'Saving…' : 'Save application' }}</button></div></form></section>
  }
  @if (loading()) { <div class="loading-state" role="status">Loading applications…</div> }
  @else {
    <section class="panel"><div class="section-heading"><h2>{{ platform ? 'Review queue' : 'Application history' }}</h2><span class="count">{{ count() }}</span></div>
      @if (!applications().length) { <div class="empty-state"><div class="empty-icon"><m-icon name="file" /></div><h3>{{ platform ? 'All clear for now.' : 'Every business starts somewhere.' }}</h3><p>{{ platform ? 'There are no applications in this view.' : 'Create your first application to get your store underway.' }}</p></div> }
      @else { <div class="table-scroll"><table><thead><tr><th>Business</th><th>{{ platform ? 'Applicant' : 'Category' }}</th><th>Status</th><th>Created</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody>@for (application of applications(); track application.id) { <tr><td><strong>{{ application.name }}</strong><small>{{ application.slug }}.localhost</small></td><td>{{ platform ? application.owner_email : application.category }}</td><td><span class="badge" [attr.data-status]="application.status">{{ application.status.replaceAll('_', ' ') | titlecase }}</span></td><td class="muted">{{ application.created_at | date:'MMM d, yyyy' }}</td><td><button class="text-button" (click)="open(application)">{{ platform ? 'Review' : 'View' }} <span aria-hidden="true">↗</span></button></td></tr> }</tbody></table></div> }
      @if (count() > applications().length) { <div class="pagination"><button mButton class="secondary compact" [disabled]="page === 1 || busy()" (click)="goPage(-1)">Previous</button><span>Page {{ page }}</span><button mButton class="secondary compact" [disabled]="!hasNext() || busy()" (click)="goPage(1)">Next</button></div> }
    </section>
  }
  @if (selected(); as application) {
    <section class="panel detail-panel"><div class="section-heading"><div><h2>{{ application.name }}</h2></div><button class="icon-button" aria-label="Close details" (click)="selected.set(null)"><m-icon name="close" /></button></div>
      <dl class="detail-grid"><div><dt>Store address</dt><dd>{{ application.slug }}.localhost</dd></div><div><dt>Contact</dt><dd>{{ application.owner_email }}<br>{{ application.phone }}</dd></div><div><dt>Location & currency</dt><dd>{{ application.country }} · {{ application.currency }}</dd></div><div><dt>Category</dt><dd>{{ application.category }}</dd></div></dl><p>{{ application.description || 'No additional description provided.' }}</p>
      @if (application.review_note) { <div class="notice"><strong>Review note</strong><p>{{ application.review_note }}</p></div> }
      @if (application.provisioning_status) { <p class="muted">Store setup: {{ application.provisioning_status }}. Approved stores go online automatically once setup is ready. Owners can take their website offline in Store settings.</p> }
      @if (platform && application.status === 'pending') { <label>Review note<textarea [(ngModel)]="note" rows="3" maxlength="2000" placeholder="Share helpful feedback with the business owner."></textarea></label><div class="review-actions"><button mButton class="secondary" [disabled]="busy()" (click)="review('changes_requested')">Request changes</button><button mButton class="danger-outline" [disabled]="busy()" (click)="review('rejected')">Reject</button><button mButton [disabled]="busy()" (click)="review('approved')"><m-icon name="check" />Approve business</button></div> }
      @if (platform && application.provisioning_status === 'failed') { <button mButton [disabled]="busy()" (click)="retry()">Retry store setup</button> }
      @if (!platform && ['draft', 'changes_requested'].includes(application.status)) { <div class="review-actions"><button mButton class="secondary" (click)="edit(application)">Edit details</button><button mButton [disabled]="busy()" (click)="submitApplication(application)">Submit for review<m-icon name="arrow" /></button></div> }
    </section>
  }
` })
export class ApplicationsPage {
  private api = inject(Api); platform = inject(PORTAL) === 'platform';
  applications = signal<Application[]>([]); selected = signal<Application | null>(null); count = signal(0); hasNext = signal(false);
  busy = signal(false); loading = signal(true); error = signal(''); message = signal(''); editing = signal(false);
  editingId = ''; note = ''; page = 1; filter = this.platform ? 'pending' : '';
  tabs = [{value:'pending',label:'Pending review'},{value:'changes_requested',label:'Changes requested'},{value:'approved',label:'Approved'},{value:'',label:'All'}];
  currencies = ['KES','UGX','TZS','RWF','USD','GBP','ZAR','NGN','GHS'];
  form = this.emptyForm();
  emptyForm() { return { name:'',slug:'',category:'',phone:'',country:'KE',currency:'KES',description:'' }; }
  constructor() { void this.load(); }
  endpoint() { return this.platform ? 'platform/applications/' : 'applications/'; }
  async load() {
    this.loading.set(true); this.error.set('');
    try { const result = await this.api.get<Page<Application>>(`${this.endpoint()}?page=${this.page}${this.filter ? '&status=' + this.filter : ''}`); this.applications.set(result.results); this.count.set(result.count); this.hasNext.set(!!result.next); }
    catch(e) { this.error.set(errorMessage(e)); } finally { this.loading.set(false); }
  }
  setFilter(value: string) { this.filter = value; this.page = 1; this.selected.set(null); void this.load(); }
  goPage(delta: number) { this.page += delta; void this.load(); }
  open(application: Application) { this.selected.set(application); this.note = ''; this.message.set(''); }
  newApplication() { this.form = this.emptyForm(); this.editingId = ''; this.editing.set(true); this.selected.set(null); this.message.set(''); }
  edit(application: Application) { this.form = { name:application.name,slug:application.slug,category:application.category,phone:application.phone,country:application.country,currency:application.currency,description:application.description || '' }; this.editingId = application.id; this.editing.set(true); }
  async action(task: () => Promise<void>) { this.busy.set(true); this.error.set(''); this.message.set(''); try { await task(); } catch(e) { this.error.set(errorMessage(e)); } finally { this.busy.set(false); } }
  async save() { await this.action(async () => { const result = await this.api.send<Application>(this.editingId ? 'PATCH' : 'POST', this.editingId ? `applications/${this.editingId}/` : 'applications/', this.form); this.editing.set(false); this.selected.set(result); this.message.set('Application saved. Submit it when you are ready.'); await this.load(); }); }
  async submitApplication(application: Application) { await this.action(async () => { this.selected.set(await this.api.send<Application>('POST', `applications/${application.id}/submit/`)); this.message.set('Your application is now with our review team.'); await this.load(); }); }
  async review(decision: string) { await this.action(async () => { const application = this.selected()!; this.selected.set(await this.api.send<Application>('POST', `${this.endpoint()}${application.id}/review/`, { decision, note: this.note })); this.message.set(decision === 'approved' ? 'Business approved. Store setup has been queued.' : 'Review saved. The applicant will receive your feedback.'); await this.load(); }); }
  async retry() { await this.action(async () => { this.selected.set(await this.api.send<Application>('POST', `${this.endpoint()}${this.selected()!.id}/retry-provisioning/`)); this.message.set('Store setup has been queued again.'); await this.load(); }); }
}
