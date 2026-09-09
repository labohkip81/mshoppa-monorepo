import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { PORTAL } from '@mshoppa/ui';
import { AdminRoot, AdminShell } from '../../../packages/ui/src/admin-shell';
import { AuthPage } from '../../../packages/ui/src/auth';
import { requireSession } from '../../../packages/ui/src/session';

bootstrapApplication(AdminRoot, { providers: [provideHttpClient(), { provide: PORTAL, useValue: 'platform' }, provideRouter([
  { path: 'login', component: AuthPage },
  { path: '', component: AdminShell, canActivate: [requireSession], children: [
    { path: 'wallet', loadComponent: () => import('../../../packages/ui/src/platform-wallet').then(m => m.PlatformWalletPage) },
    { path: '', loadComponent: () => import('../../../packages/ui/src/applications').then(m => m.ApplicationsPage) },
  ] },
  { path: '**', redirectTo: '' },
])] }).catch(console.error);
