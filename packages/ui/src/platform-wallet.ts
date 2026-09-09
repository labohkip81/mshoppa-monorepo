import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api, errorMessage } from '@mshoppa/api';
import { Button } from './index';
import { Withdrawal } from './payment-workspace';

interface Settlement {order_id:string;business:string;amount:string;currency:string}
@Component({standalone:true,imports:[FormsModule,Button],styleUrl:'./payment-workspace.css',template:`
  <div class="page-heading"><div><h1>Wallet operations</h1><p>Reconcile settlements and review withdrawal requests.</p></div><button mButton class="secondary" [disabled]="busy()" (click)="load()">Refresh</button></div>
  @if(error()){<div class="notice error" role="alert">{{error()}}</div>}@if(message()){<div class="notice success" role="status">{{message()}}</div>}
  @if(loading()){<p class="loading-state">Loading wallet operations…</p>}@else{
  <section class="panel withdrawal-panel"><div class="config-heading"><div><h2>Collections awaiting settlement</h2><p>Record the net amount only after confirming it has settled into the account used to fund withdrawals.</p></div></div>
  @for(row of settlements();track row.order_id){<article class="withdrawal-panel"><h3>{{row.business}} · #{{row.order_id.slice(0,8).toUpperCase()}}</h3><p class="payment-note">Collected: {{row.currency}} {{row.amount}}</p><form ngNativeValidate (ngSubmit)="settle(row)"><fieldset [disabled]="busy()"><div class="form-grid"><label>Net settled amount<input type="number" name="amount" min="0.01" [max]="row.amount" step="0.01" [(ngModel)]="amounts[row.order_id]" required></label><label>Settlement reference<input name="reference" [(ngModel)]="references[row.order_id]" maxlength="200" required></label></div><button mButton>Confirm settlement</button></fieldset></form></article>}@empty{<p class="payment-note">No live collections awaiting settlement.</p>}</section>
  <section class="panel withdrawal-panel"><div class="config-heading"><div><h2>Pending withdrawals</h2><p>Make the transfer through the authorised provider, then record its confirmed reference here. These controls do not send money.</p></div></div>
  @for(row of withdrawals();track row.id){<article class="withdrawal-panel"><h3>{{row.business_name}} · {{row.currency}} {{row.amount}}</h3><p class="payment-note">{{row.recipient_name}} · {{row.method==='mpesa'?'M-Pesa '+row.phone:row.bank_name+' · '+row.account_number}}</p><form ngNativeValidate (ngSubmit)="review(row)"><fieldset [disabled]="busy()"><div class="form-grid"><label>Review outcome<select name="status" [(ngModel)]="statuses[row.id]"><option value="completed">Transfer completed</option><option value="rejected">Reject request</option></select></label><label>Confirmed transfer reference<input name="reference" [(ngModel)]="references[row.id]" maxlength="200" [required]="statuses[row.id]==='completed'"></label></div><label>Review note<textarea name="note" [(ngModel)]="notes[row.id]" maxlength="500" [required]="statuses[row.id]==='rejected'"></textarea></label><button mButton>Record outcome</button></fieldset></form></article>}@empty{<p class="payment-note">No withdrawal requests awaiting review.</p>}</section>}
`})
export class PlatformWalletPage {
  api=inject(Api); settlements=signal<Settlement[]>([]);withdrawals=signal<Withdrawal[]>([]);loading=signal(true);busy=signal(false);error=signal('');message=signal('');amounts:Record<string,string>={};references:Record<string,string>={};statuses:Record<string,string>={};notes:Record<string,string>={};
  constructor(){void this.load();}
  async load(){this.loading.set(true);this.error.set('');try{const result=await this.api.get<{settlements:Settlement[];withdrawals:Withdrawal[]}>('platform/wallet/');this.settlements.set(result.settlements);this.withdrawals.set(result.withdrawals);this.statuses=Object.fromEntries(result.withdrawals.map(row=>[row.id,'completed']));}catch(e){this.error.set(errorMessage(e));}finally{this.loading.set(false);}}
  async run(path:string,data:unknown,message:string){if(this.busy())return;this.busy.set(true);this.error.set('');this.message.set('');try{await this.api.send('POST',path,data);await this.load();this.message.set(message);}catch(e){this.error.set(errorMessage(e));}finally{this.busy.set(false);}}
  settle(row:Settlement){void this.run('platform/wallet/',{order_id:row.order_id,amount:this.amounts[row.order_id],reference:this.references[row.order_id]},'Settlement recorded. The net funds are now available in the store wallet.');}
  review(row:Withdrawal){void this.run('platform/withdrawals/'+row.id+'/review/',{status:this.statuses[row.id],transfer_reference:this.references[row.id]||'',review_note:this.notes[row.id]||''},'Withdrawal outcome recorded.');}
}
