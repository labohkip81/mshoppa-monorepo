import { Component, Directive, InjectionToken, input } from '@angular/core';
import { BrnButton } from '@spartan-ng/brain/button';

export const PORTAL = new InjectionToken<'merchant' | 'platform'>('portal');

export const SOCIAL_PROFILES = [
  {key:'instagram_url',label:'Instagram',icon:'instagram',placeholder:'https://www.instagram.com/yourstore'},
  {key:'facebook_url',label:'Facebook',icon:'facebook',placeholder:'https://www.facebook.com/yourstore'},
  {key:'tiktok_url',label:'TikTok',icon:'tiktok',placeholder:'https://www.tiktok.com/@yourstore'},
  {key:'x_url',label:'X',icon:'x',placeholder:'https://x.com/yourstore'},
  {key:'linkedin_url',label:'LinkedIn',icon:'linkedin',placeholder:'https://www.linkedin.com/company/yourstore'},
] as const;

@Directive({ selector: 'button[mButton], a[mButton]', standalone: true, hostDirectives: [{ directive: BrnButton, inputs: ['disabled'] }], host: { class: 'button' } })
export class Button {}

@Component({ selector: 'm-logo', standalone: true, template: '<img src="/brand/mshoppa-logo-reference.png" alt="MSHOPPA" width="1674" height="314">', styles: [':host {display:inline-flex;width:142px;align-items:center} img{width:100%;height:auto;display:block}'] })
export class Logo {}

@Component({ selector: 'm-icon', standalone: true, template: '<svg viewBox="0 0 24 24" [attr.fill]="name() === \'whatsapp\' ? \'#25D366\' : \'none\'" [attr.stroke]="name() === \'whatsapp\' ? \'none\' : \'currentColor\'" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path [attr.d]="paths[name()] || paths[\'grid\']" /></svg>', styles: [':host{display:inline-flex;width:20px;height:20px;flex-shrink:0}svg{width:100%;height:100%}'] })
export class Icon {
  name = input('grid');
  paths: Record<string, string> = {
    // WhatsApp brand glyph: https://github.com/simple-icons/simple-icons/blob/develop/icons/whatsapp.svg
    whatsapp: 'M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z',
    store: 'M3 10h18 M4 10v11h16V10 M3 10l2-7h14l2 7 M9 21v-7h6v7 M8 3l-1 7 M16 3l1 7',
    card: 'M3 5h18v14H3z M3 10h18 M6 15h4',
    users: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M17 3a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-3.87',
    tag: 'M3 3h8l10 10-8 8L3 11V3Z M7 7h.01',
    instagram: 'M7 3h10a4 4 0 0 1 4 4v10a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4Z M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M17.5 6.5h.01',
    facebook: 'M14 21v-8h3l.5-4H14V7c0-1 .5-1.5 1.5-1.5H18V2.2L15.3 2C12 2 10 4 10 7v2H7v4h3v8',
    tiktok: 'M14 3h3c0 3 2 5 5 5v3a9 9 0 0 1-5-2v7a6 6 0 1 1-6-6v3a3 3 0 1 0 3 3V3Z',
    x: 'M4 3h4l12 18h-4L4 3Z M20 3l-6.6 8 M10.6 13 4 21',
    linkedin: 'M4 9h3v12H4V9Z M4 3h3v3H4V3Z M11 21V9h3v2c1-2 6-3 6 3v7h-3v-7c0-2-3-2-3 0v7h-3Z',
    grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    bag: 'M5 7h14l1 14H4L5 7Z M8 7V6a4 4 0 0 1 8 0v1',
    box: 'm12 3 9 5-9 5-9-5 9-5Z M3 8v10l9 5 9-5V8 M12 13v10 M7.5 5.5l9 5v5',
    settings: 'M4 7h16 M4 17h16 M8 4v6 M16 14v6',
    arrow: 'M4 12h16 M14 6l6 6-6 6',
    check: 'm5 12 4 4L19 6',
    plus: 'M12 5v14 M5 12h14',
    logout: 'M9 4H4v16h5 M10 12h11 M17 8l4 4-4 4',
    file: 'M14 2H5v20h14V7l-5-5Z M14 2v6h5 M8 12h8 M8 16h6',
    globe: 'M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0 M3 12h18 M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z',
    shield: 'm12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z m-4 9 3 3 5-5',
    search: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14 M15 15l6 6',
    mail: 'M3 5h18v14H3z m0 1 9 7 9-7',
    phone: 'M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.12 4.2 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.12.96.35 1.9.69 2.79a2 2 0 0 1-.45 2.11L8.09 9.89a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.89.34 1.83.57 2.79.69A2 2 0 0 1 22 16.92Z',
    menu: 'M4 6h16 M4 12h16 M4 18h16',
    close: 'm6 6 12 12 M18 6 6 18'
  };
}
