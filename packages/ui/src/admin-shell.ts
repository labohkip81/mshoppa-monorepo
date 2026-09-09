import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { Api, errorMessage } from '@mshoppa/api';
import { Button, Icon, Logo, PORTAL } from './index';
import { Workspace } from './session';

@Component({ selector: 'mshoppa-root', standalone: true, imports: [RouterOutlet], template: '<router-outlet />' })
export class AdminRoot {}

@Component({ standalone: true, imports: [RouterOutlet, RouterLink, RouterLinkActive, Icon, Logo, Button], template: `
  <div class="admin-layout" [class.nav-open]="menu()">
    @if (menu()) { <button class="nav-scrim" aria-label="Close navigation" (click)="menu.set(false)"></button> }
    <aside class="sidebar" id="workspace-navigation" (keydown.escape)="menu.set(false)">
      <a routerLink="/" class="sidebar-brand"><m-logo /></a>
      <div class="workspace-label"><span class="workspace-avatar">{{ platform ? 'M' : 'B' }}</span><div><strong>{{ platform ? 'Platform workspace' : 'Business workspace' }}</strong><small>{{ platform ? 'Operations & approvals' : 'A little more possibility' }}</small></div></div>
      <span class="nav-caption">WORKSPACE</span>
      <nav aria-label="Main navigation" (click)="menu.set(false)">
        @if (platform) {
          <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{exact:true}"><m-icon name="file" />Applications</a>
          <a routerLink="/wallet" routerLinkActive="active"><m-icon name="card" />Wallet operations</a>
        } @else {
          <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{exact:true}"><m-icon name="grid" />Overview</a>
          <a routerLink="/products" routerLinkActive="active"><m-icon name="box" />Products</a>
          <a routerLink="/orders" routerLinkActive="active"><m-icon name="bag" />Orders</a>
          <a routerLink="/businesses" routerLinkActive="active"><m-icon name="store" />Businesses</a>
          <a routerLink="/payments" routerLinkActive="active"><m-icon name="card" />Payments</a>
          <a routerLink="/customers" routerLinkActive="active"><m-icon name="users" />Customers</a>
          <a routerLink="/promotions" routerLinkActive="active"><m-icon name="tag" />Promotions</a>
          <a routerLink="/staff" routerLinkActive="active"><m-icon name="shield" />Staff</a>
          <a routerLink="/applications" routerLinkActive="active"><m-icon name="file" />Applications</a>
          <a routerLink="/settings" routerLinkActive="active"><m-icon name="settings" />Store settings</a>
        }
      </nav>
      <div class="sidebar-bottom"><div class="phase-note"><span class="status-dot"></span>Early access<span>Foundation release</span></div><button class="user-menu" (click)="logout()"><span class="avatar">{{ api.user()?.first_name?.slice(0,1) || 'M' }}</span><div><strong>{{ api.user()?.first_name || 'Your account' }}</strong><small>{{ api.user()?.email }}</small></div><m-icon name="logout" /></button></div>
    </aside>
    <section class="main-column">
      <header class="topbar"><div class="inline"><button class="icon-button mobile-only" aria-label="Open navigation" aria-controls="workspace-navigation" [attr.aria-expanded]="menu()" (click)="menu.set(true)"><m-icon name="menu" /></button><span>{{ platform ? 'Platform' : 'Your workspace' }}</span><span class="breadcrumb-divider">/</span><strong>{{ title() }}</strong></div><div class="topbar-actions">@if (!platform) { @if (workspace.publicStoreUrl(); as url) { <a mButton class="secondary compact" [href]="url" target="_blank" rel="noopener noreferrer" [title]="'Open ' + workspace.selected()?.name + ' in a new tab'"><m-icon name="globe" />View shop <span aria-hidden="true">↗</span></a> } @else { <button mButton class="secondary compact" disabled title="Your shop must be online and have a verified domain to view it."><m-icon name="globe" />View shop</button> } }</div></header>
      @if (error()) { <div class="notice error" role="alert">{{ error() }}</div> }
      <main class="admin-main" id="main-content"><router-outlet /></main>
      <footer class="workspace-footer"><span>Built for the way you do business.</span><span>MSHOPPA · {{ year }}</span></footer>
    </section>
  </div>` })
export class AdminShell {
  api = inject(Api); router = inject(Router); platform = inject(PORTAL) === 'platform';
  workspace = inject(Workspace);
  constructor() { if (!this.platform) void this.workspace.load().catch(e => this.error.set(errorMessage(e))); }
  menu = signal(false); error = signal(''); year = new Date().getFullYear();
  title() { const path = this.router.url.split('?')[0].split('/')[1]; return ({wallet:'Wallet operations',applications:'Applications',products:'Products',orders:'Orders',businesses:'Businesses',payments:'Payments',customers:'Customers',staff:'Staff',promotions:'Promotions',settings:'Store settings'} as Record<string,string>)[path] || (this.platform ? 'Applications' : 'Overview'); }
  async logout() { try { await this.api.logout(); await this.router.navigateByUrl('/login'); } catch (e) { this.error.set(errorMessage(e)); } }
}
