import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { PORTAL } from '@mshoppa/ui';
import { AdminRoot, AdminShell } from '../../../packages/ui/src/admin-shell';
import { AuthPage } from '../../../packages/ui/src/auth';
import { requireSession } from '../../../packages/ui/src/session';

bootstrapApplication(AdminRoot, { providers: [provideHttpClient(), { provide: PORTAL, useValue: 'merchant' }, provideRouter([
  { path: 'login', component: AuthPage },
  { path: 'signup', component: AuthPage, data: { mode: 'signup' } },
  { path: 'verify-email', component: AuthPage, data: { mode: 'verify' } },
  { path: '', component: AdminShell, canActivate: [requireSession], children: [
    { path: '', pathMatch: 'full', loadComponent: () => import('../../../packages/ui/src/merchant').then(m => m.OverviewPage) },
    { path: 'products', loadComponent: () => import('../../../packages/ui/src/products').then(m => m.ProductsPage) },
    ...['orders', 'businesses', 'payments', 'customers', 'staff', 'promotions'].map(section => ({
      path: section, data: { section }, loadComponent: () => import('../../../packages/ui/src/management').then(m => m.ManagementPage),
    })),
    { path: 'settings', loadComponent: () => import('../../../packages/ui/src/merchant').then(m => m.SettingsPage) },
    { path: 'applications', loadComponent: () => import('../../../packages/ui/src/applications').then(m => m.ApplicationsPage) },
  ] },
  { path: '**', redirectTo: '' },
])] }).catch(console.error);
