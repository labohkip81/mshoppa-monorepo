import { Component } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter, RouterLink, RouterOutlet } from '@angular/router';
import { Button, Icon, Logo, PORTAL } from '@mshoppa/ui';
import { AuthPage } from '../../../packages/ui/src/auth';

@Component({ standalone: true, imports: [RouterLink, Button, Icon, Logo], template: `
  <div class="marketing"><header class="marketing-nav"><a routerLink="/" aria-label="MSHOPPA home"><m-logo /></a><nav><a href="http://admin.localhost:4201/login">Sign in</a><a mButton routerLink="/signup">Get started <m-icon name="arrow" /></a></nav></header>
  <main><section class="marketing-hero"><div><h1>Your business.<br>Your people.<br><em>Your own space.</em></h1><p>Make a home for what you do. A thoughtful online store, built around your business.</p><a mButton routerLink="/signup">Start your next chapter <m-icon name="arrow" /></a><span class="field-hint">Early access · Apply to join MSHOPPA</span></div><div class="marketing-art" aria-label="Illustration of a minimal independent storefront"><div class="mini-browser"><div class="mini-dots"><i></i><i></i><i></i><span>your-business.mshoppa.com</span></div><div class="mini-brand">EVERYDAY STUDIO</div><div class="mini-title">Good things,<br>made for everyday.</div><div class="mini-tiles"><div></div><div></div><div></div></div><div class="mini-line"></div><div class="mini-line short"></div></div><span class="floating-label"><m-icon name="check" />An idea, with a place to grow.</span></div></section>
  <section class="marketing-features" aria-label="A simpler start"><div><m-icon name="globe" /><h2>A storefront that feels like you.</h2><p>Start with a calm, considered design. Add your own story, your products and your point of view.</p></div><div><m-icon name="box" /><h2>Less noise. More clarity.</h2><p>Build your collection from one simple workspace. The essentials, with room to grow.</p></div><div><m-icon name="shield" /><h2>A thoughtful beginning.</h2><p>Apply, meet our review team, and get your business ready for its next chapter.</p></div></section></main>
  <footer class="marketing-footer"><span>© {{ year }} MSHOPPA</span><span>Independent businesses. Endless possibility.</span></footer></div>
` })
class Landing { year = new Date().getFullYear(); }

@Component({ selector: 'mshoppa-root', standalone: true, imports: [RouterOutlet], template: '<router-outlet />' })
class MarketingRoot {}
bootstrapApplication(MarketingRoot, { providers: [provideHttpClient(), { provide: PORTAL, useValue: 'merchant' }, provideRouter([
  { path: '', component: Landing }, { path: 'signup', component: AuthPage, data: { mode:'signup' } }, { path: 'login', component: AuthPage }, { path:'**', redirectTo:'' }
])] }).catch(console.error);
