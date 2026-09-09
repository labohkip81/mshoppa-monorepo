import { Component, effect, inject, output, signal } from '@angular/core';
import { DatePipe, TitleCasePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Api, errorMessage } from '@mshoppa/api';
import { Button, Icon } from './index';
import { Workspace } from './session';

interface PaymentSource {enabled:boolean; use_platform_defaults:boolean; source:'mshoppa'|'store'; ready:boolean}
interface PaymentConfiguration {
  stripe:PaymentSource & { secret_key_saved:boolean; webhook_secret_saved:boolean};
  mpesa:PaymentSource & { tenant_id:string; api_token_saved:boolean; callback_secret_saved:boolean; callback_url:string; use_default_config:boolean};
}
export interface Withdrawal { id:string; business_name:string; amount:string; currency:string; method:string; recipient_name:string; phone:string; bank_name:string; account_number:string; status:string; transfer_reference:string; review_note:string; created_at:string }
interface Wallet {currency:string;collected:string;awaiting_settlement:string;settled:string;reserved:string;withdrawn:string;available:string;test_payments:string;withdrawals:Withdrawal[]}

@Component({selector:'m-payment-workspace',standalone:true,imports:[FormsModule,DatePipe,TitleCasePipe,Button,Icon],templateUrl:'./payment-workspace.html',styleUrl:'./payment-workspace.css'})
export class PaymentWorkspace {
  api=inject(Api); workspace=inject(Workspace); transactions=output<boolean>();
  tab=signal('overview'); loading=signal(false); busy=signal(false); error=signal(''); message=signal('');
  configuration=signal<PaymentConfiguration|null>(null); wallet=signal<Wallet|null>(null);
  stripe={enabled:true,use_platform_defaults:true,secret_key:'',webhook_secret:''};
  mpesa={enabled:true,use_platform_defaults:true,tenant_id:'',api_token:'',use_default_config:false,callback_url:'',callback_secret:''};
  withdrawal={amount:'',method:'mpesa',recipient_name:'',phone:'',bank_name:'',account_number:''};
  reviewing=signal(false); requestKey=''; private generation=0;
  constructor(){effect(()=>{const id=this.workspace.selected()?.id;if(id){this.tab.set('overview');this.message.set('');this.transactions.emit(true);this.reviewing.set(false);this.configuration.set(null);this.wallet.set(null);this.stripe={enabled:true,use_platform_defaults:true,secret_key:'',webhook_secret:''};this.mpesa={enabled:true,use_platform_defaults:true,tenant_id:'',api_token:'',use_default_config:false,callback_url:'',callback_secret:''};this.withdrawal={amount:'',method:this.workspace.selected()?.currency==='KES'?'mpesa':'bank',recipient_name:'',phone:'',bank_name:'',account_number:''};void this.load(id);}});}
  owner(){return this.workspace.selected()?.role==='owner';}
  editable(){return this.owner()&&!this.workspace.selected()?.suspended;}
  endpoint(id=this.workspace.selected()!.id){return `businesses/${id}/payments/`;}
  choose(tab:string){if(this.busy())return;this.tab.set(tab);this.transactions.emit(tab==='overview');this.error.set('');this.message.set('');this.reviewing.set(false);}
  async load(id=this.workspace.selected()!.id){
    const generation=++this.generation;this.loading.set(true);this.error.set('');
    const [config,balance]=await Promise.allSettled([this.api.get<PaymentConfiguration>(this.endpoint(id)+'configuration/'),this.owner()?this.api.get<Wallet>(this.endpoint(id)+'wallet/'):Promise.resolve(null)]);
    if(generation!==this.generation)return;
    const errors:string[]=[];
    if(config.status==='fulfilled'){
      this.configuration.set(config.value);this.applyConfiguration('stripe',config.value);this.applyConfiguration('mpesa',config.value);
    }else{errors.push(errorMessage(config.reason));}
    if(balance.status==='fulfilled')this.wallet.set(balance.value);else{this.wallet.set(null);errors.push(errorMessage(balance.reason));}
    this.error.set(errors.join(' '));this.loading.set(false);
  }

  applyConfiguration(provider:'stripe'|'mpesa',config:PaymentConfiguration){if(provider==='stripe'){this.stripe={enabled:config.stripe.enabled,use_platform_defaults:config.stripe.use_platform_defaults,secret_key:'',webhook_secret:''};}else{this.mpesa={enabled:config.mpesa.enabled,use_platform_defaults:config.mpesa.use_platform_defaults,tenant_id:config.mpesa.tenant_id,use_default_config:config.mpesa.use_default_config,callback_url:config.mpesa.callback_url,api_token:'',callback_secret:''};}}
  async save(provider:'stripe'|'mpesa'){if(this.busy()||!this.editable())return;const id=this.workspace.selected()!.id;this.busy.set(true);this.error.set('');this.message.set('');try{const config=await this.api.send<PaymentConfiguration>('PATCH',this.endpoint(id)+'configuration/',{provider,values:{...this[provider]}});if(id!==this.workspace.selected()?.id)return;this.configuration.set(config);this.applyConfiguration(provider,config);this.message.set(`${provider==='stripe'?'Stripe':'M-Pesa'} configuration saved.`);}catch(e){if(id===this.workspace.selected()?.id)this.error.set(errorMessage(e));}finally{this.busy.set(false);}}
  money(value:string,currency=this.workspace.selected()?.currency||'KES'){return `${currency} ${Number(value).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`;}
  prepareWithdrawal(){this.error.set('');if(!this.editable()||!this.wallet())return;const amount=Number(this.withdrawal.amount);if(!Number.isFinite(amount)||amount<=0||amount>Number(this.wallet()!.available)){this.error.set('Enter an amount within your available settled balance.');return;}this.requestKey=crypto.randomUUID();this.reviewing.set(true);}
  async requestWithdrawal(){if(this.busy()||!this.reviewing())return;const id=this.workspace.selected()!.id;this.busy.set(true);this.error.set('');try{await this.api.send('POST',this.endpoint(id)+'wallet/',{...this.withdrawal,request_key:this.requestKey});if(id!==this.workspace.selected()?.id)return;this.reviewing.set(false);this.withdrawal.amount='';await this.load(id);this.message.set('Withdrawal requested. Funds are reserved while it awaits review.');}catch(e){if(id===this.workspace.selected()?.id)this.error.set(errorMessage(e));}finally{this.busy.set(false);}}
  async cancel(row:Withdrawal){if(this.busy())return;const id=this.workspace.selected()!.id;this.busy.set(true);this.error.set('');try{await this.api.send('POST',this.endpoint(id)+`withdrawals/${row.id}/cancel/`,{});if(id!==this.workspace.selected()?.id)return;await this.load(id);this.message.set('Withdrawal cancelled. The reserved funds are available again.');}catch(e){if(id===this.workspace.selected()?.id)this.error.set(errorMessage(e));}finally{this.busy.set(false);}}
}
