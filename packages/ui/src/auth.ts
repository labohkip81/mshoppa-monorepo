import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Api, errorMessage, User } from '@mshoppa/api';
import { Button, Icon, Logo, PORTAL } from './index';

@Component({ standalone: true, imports: [FormsModule, RouterLink, Button, Icon, Logo], template: `
  <div class="auth-page">
    <a class="auth-brand" href="http://localhost:4200"><m-logo /></a>
    <div class="auth-card">

      <h1>{{ mode === 'signup' ? 'Make room for what’s next.' : mode === 'verify' ? 'One last step.' : mfa() ? 'A little extra security.' : 'Welcome back.' }}</h1>
      <p class="muted">{{ mode === 'signup' ? 'Create your account. Build something of your own.' : mode === 'verify' ? 'Verify your email to continue to your workspace.' : mfa() ? 'Enter the six-digit code from your authenticator app.' : 'Your store, your people, your next chapter.' }}</p>
      @if (error()) { <div class="notice error" role="alert">{{ error() }}</div> }
      @if (message()) { <div class="notice success" role="status">{{ message() }}</div> }
      @if (mode === 'verify') {
        <button mButton class="full" (click)="verify()" [disabled]="busy() || !!message()">{{ busy() ? 'Verifying…' : 'Verify email' }}<m-icon name="check" /></button>
        <a routerLink="/login" class="text-link">Continue to sign in <span>↗</span></a>
      } @else if (!message()) {
        <form (ngSubmit)="submit()">
          @if (mfa()) {
            @if (secret()) { <div class="notice"><strong>Set up your authenticator</strong><p>Add a time-based account named MSHOPPA using this setup key. Keep it private.</p><code class="setup-key">{{ secret() }}</code></div> }
            <label>Authentication code<input name="code" [(ngModel)]="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required placeholder="000000"></label>
          } @else {
            @if (mode === 'signup') { <div class="form-grid"><label>First name<input name="first_name" [(ngModel)]="firstName" autocomplete="given-name" required maxlength="150"></label><label>Last name<input name="last_name" [(ngModel)]="lastName" autocomplete="family-name" required maxlength="150"></label></div> }
            <label>Email address<input name="email" type="email" [(ngModel)]="email" autocomplete="email" placeholder="you@yourbusiness.com" required></label>
            <label>Password<input name="password" type="password" [(ngModel)]="password" [attr.autocomplete]="mode === 'signup' ? 'new-password' : 'current-password'" [minlength]="mode === 'signup' ? 10 : 1" required placeholder="Enter your password"></label>
            @if (mode === 'signup') { <p class="field-hint">Use at least 10 characters and avoid common passwords.</p> }
          }
          <button mButton class="full" [disabled]="busy()">{{ busy() ? 'Please wait…' : mfa() ? 'Verify & sign in' : mode === 'signup' ? 'Create account' : 'Sign in' }} <m-icon name="arrow" /></button>
        </form>
      }
      @if (!platform && mode !== 'verify' && !mfa()) { <p class="auth-switch">{{ mode === 'signup' ? 'Already have an account?' : 'New to MSHOPPA?' }} <a [routerLink]="mode === 'signup' ? '/login' : '/signup'">{{ mode === 'signup' ? 'Sign in' : 'Create an account' }}</a></p> }
      <div class="auth-security"><m-icon name="shield" /><span>{{ platform ? 'Staff access requires two-step verification.' : 'A considered home for your business.' }}</span></div>
    </div>
    <div class="auth-footer"><span>© {{ year }} MSHOPPA</span><span>Made for independent businesses.</span></div>
  </div>` })
export class AuthPage {
  private api = inject(Api); private router = inject(Router); private route = inject(ActivatedRoute);
  platform = inject(PORTAL, { optional: true }) === 'platform';
  mode = this.route.snapshot.data['mode'] || 'login';
  year = new Date().getFullYear();
  busy = signal(false); error = signal(''); message = signal(''); mfa = signal(false); secret = signal('');
  firstName = ''; lastName = ''; email = ''; password = ''; code = '';
  async verify() {
    this.busy.set(true); this.error.set('');
    try { const response = await this.api.send<{ detail: string }>('POST', 'auth/verify-email/', { token: this.route.snapshot.queryParamMap.get('token') || '' }); this.message.set(response.detail); }
    catch (e) { this.error.set(errorMessage(e)); } finally { this.busy.set(false); }
  }
  async submit() {
    this.busy.set(true); this.error.set('');
    try {
      if (this.mode === 'signup') {
        const response = await this.api.send<{ detail: string }>('POST', 'auth/register/', { first_name: this.firstName, last_name: this.lastName, email: this.email, password: this.password });
        this.password = ''; this.message.set(response.detail); return;
      }
      const response = await this.api.send<{ user?: User; requires_mfa?: boolean; requires_mfa_setup?: boolean }>('POST', this.mfa() ? 'auth/mfa/verify/' : 'auth/login/', this.mfa() ? { code: this.code } : { email: this.email, password: this.password });
      this.password = '';
      if (response.requires_mfa) {
        this.mfa.set(true);
        if (response.requires_mfa_setup) { const setup = await this.api.send<{ secret: string }>('POST', 'auth/mfa/setup/'); this.secret.set(setup.secret); }
      } else if (response.user) {
        this.api.user.set(response.user);
        if (this.platform && !response.user.is_staff) { await this.api.logout(); this.error.set('This portal is for MSHOPPA staff. Use the business workspace to manage your store.'); return; }
        await this.router.navigateByUrl('/');
      }
    } catch (e) { this.error.set(errorMessage(e)); } finally { this.busy.set(false); }
  }
}
