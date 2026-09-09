import { Component, ChangeDetectorRef, inject, signal, OnDestroy } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient } from '@angular/common/http';
import { Api, errorMessage, Product, StoreSettings } from '@mshoppa/api';
import { Icon, SOCIAL_PROFILES } from '@mshoppa/ui';
import { CartService, CartControls, StoreCheckout } from './commerce';
import { RichTextPipe } from '../../../packages/ui/src/rich-text';

interface Store { id:string; name:string; phone:string; currency:string; preview:boolean; settings:StoreSettings; products:Product[]; featured_product:Product | null; products_count:number; has_more:boolean; categories:string[]; product?:Product }
@Component({ selector:'mshoppa-root', standalone:true, imports:[DecimalPipe,Icon,CartControls,StoreCheckout,RichTextPipe], template:`
  @if (loading()) { <main class="store-unavailable" role="status"><span class="store-wordmark">A little moment.</span><p>Opening the store…</p></main> }
  @else if (store(); as shop) {
    @if (shop.preview) { <div class="preview-banner">PRIVATE PREVIEW · Includes drafts. Shopping is not enabled.</div> }
    <header class="store-nav" id="top"><a class="store-wordmark" [href]="(shop.product || checkoutPage) ? '/' : '#top'" [attr.aria-label]="shop.name + ' home'">@if (shop.settings.logo_url) { <img class="nav-store-logo" [src]="shop.settings.logo_url" [alt]="shop.name"> } @else { <span class="nav-store-monogram">{{ shop.name.slice(0,1) }}</span><span>{{ shop.name }}</span> }</a>@if (!shop.product && !checkoutPage) { <label class="store-search nav-search"><m-icon name="search" /><input type="search" aria-label="Search products" placeholder="Search for products" [value]="query()" (input)="search($event)" maxlength="180" aria-controls="product-results">@if (query()) { <button type="button" (click)="clearSearch()" aria-label="Clear product search">×</button> }</label> } @else { <nav><a href="/#products">Browse products</a></nav> }<div class="store-header-actions">@if (shop.phone) { <a class="store-phone" [href]="phoneHref(shop.phone)" [attr.aria-label]="'Call ' + shop.name"><m-icon name="phone" /></a> }@if (whatsappHref(true); as whatsapp) { <a class="store-header-whatsapp" [href]="whatsapp" target="_blank" rel="noopener noreferrer" [attr.aria-label]="'Chat with ' + shop.name + ' on WhatsApp'" title="Chat on WhatsApp"><m-icon name="whatsapp" /></a> }@if (!shop.preview) { <m-cart-controls /> }</div></header>
    <main>@if (checkoutPage && !shop.preview) { <m-store-checkout /> } @else if (shop.product; as product) {
      <section class="store-product-detail"><a class="product-back" href="/#products">← All products</a><div class="product-detail-grid"><div><div class="product-detail-image" [style.background]="product.images[detailImage()] ? null : tone()">@if (product.images[detailImage()]; as image) { <img [src]="image.url" [alt]="product.name" [width]="image.width" [height]="image.height" fetchpriority="high"> } @else { <m-icon name="box" /> }</div>@if (product.images.length > 1) { <div class="product-detail-thumbnails">@for (image of product.images; track image.id; let index = $index) { <button type="button" [attr.aria-label]="'View product image ' + (index + 1)" [attr.aria-pressed]="detailImage() === index" (click)="detailImage.set(index)"><img [src]="image.url" alt="" loading="lazy" width="64" height="64"></button> }</div> }</div><div class="product-detail-info">@if (product.category) { <span class="store-caption">{{ product.category }}</span> }<h1>{{ product.name }}</h1>@if (product.has_variants) { <label class="store-variant-picker">Variant<select [value]="chosenVariant(product)?.id" (change)="chooseVariant(product,$event)">@for (option of product.variants; track option.id) { <option [value]="option.id">{{ option.label }}{{ !option.stock ? ' — sold out' : '' }}</option> }</select></label> }@if (chosenVariant(product); as variant) { <div class="store-price"><p><span class="price-currency">{{ shop.currency }}</span> {{ (variant.offer_price ?? variant.price) | number:priceDigits() }}</p>@if (variant.offer_price !== null && variant.offer_price !== undefined) { <del>{{ shop.currency }} {{ variant.price | number:priceDigits() }}</del><span class="store-offer">Offer</span> }</div> }@if (product.description) { <div class="product-description rich-content" [innerHTML]="product.description | richText"></div> }<button type="button" class="store-button add-to-cart" [disabled]="!chosenVariant(product)?.stock" (click)="cart.add(product,chosenVariant(product))">{{ chosenVariant(product)?.stock ? 'Add to cart' : 'Out of stock' }}<m-icon name="bag" /></button></div></div></section>
    } @else {
      <section class="shop-profile" aria-labelledby="shop-title" [style.--brand-tone]="tone()">
        <div class="shop-cover" [class.has-cover]="!!shop.settings.cover_url">@if (shop.settings.cover_url) { <img [src]="shop.settings.cover_url" [alt]="shop.name + ' cover'" fetchpriority="high" decoding="async"> } @else { <div class="cover-orbit orbit-one" aria-hidden="true"></div><div class="cover-orbit orbit-two" aria-hidden="true"></div> }</div>
        <div class="shop-profile-content"><div class="shop-profile-top"><div class="shop-profile-logo">@if (shop.settings.logo_url) { <img [src]="shop.settings.logo_url" [alt]="shop.name + ' logo'"> } @else { <span aria-hidden="true">{{ shop.name.slice(0,1) }}</span> }</div><nav class="shop-socials" aria-label="Follow this store">@for (social of socialLinks(); track social.label) { <a [href]="social.url" [attr.aria-label]="social.label" [attr.data-social]="social.icon" target="_blank" rel="noopener noreferrer"><m-icon [name]="social.icon" /></a> }</nav></div><h1 id="shop-title">{{ shop.name }}</h1>@if (shop.settings.description) { <div class="shop-description rich-content" [innerHTML]="shop.settings.description | richText"></div> } @else if (shop.settings.headline) { <p class="shop-description">{{ shop.settings.headline }}</p> }</div>
      </section>
      <section class="collection" id="products" aria-labelledby="products-heading"><div class="collection-heading"><h2 id="products-heading" class="collection-tab"><m-icon name="box" />Products <span role="status" aria-live="polite">{{ shop.products_count }}</span></h2><div class="collection-controls"><div class="mobile-product-search" [class.expanded]="mobileSearchOpen()" (keydown.escape)="closeMobileSearch(mobileSearchToggle)"><button #mobileSearchToggle type="button" class="mobile-search-toggle" aria-label="Search products" aria-controls="mobile-product-search" [attr.aria-expanded]="mobileSearchOpen()" (click)="openMobileSearch(mobileSearchInput)"><m-icon name="search" /><span class="mobile-search-label">Search</span></button><input #mobileSearchInput id="mobile-product-search" type="search" aria-label="Search products" placeholder="Search products" autocomplete="off" enterkeyhint="search" maxlength="180" [value]="query()" [disabled]="!mobileSearchOpen()" [attr.tabindex]="mobileSearchOpen() ? 0 : -1" aria-controls="product-results" (input)="search($event)"><button type="button" class="mobile-search-close" aria-label="Close and clear product search" [disabled]="!mobileSearchOpen()" (click)="closeMobileSearch(mobileSearchToggle)"><m-icon name="close" /></button></div><label class="store-sort"><span>Sort by</span><select aria-label="Sort products" [value]="sort()" (change)="changeSort($event)"><option value="featured">Featured</option><option value="latest">Newest</option><option value="name">Name: A–Z</option><option value="price-low">Price: low to high</option><option value="price-high">Price: high to low</option></select></label></div></div>
      @if (shop.categories.length) { <nav class="shop-categories" aria-label="Product categories"><button type="button" [class.active]="!category()" [attr.aria-pressed]="!category()" (click)="chooseCategory('')">All</button>@for (item of shop.categories; track item) { <button type="button" [class.active]="category() === item" [attr.aria-pressed]="category() === item" (click)="chooseCategory(item)">{{ item }}</button> }</nav> }
    <div id="product-results" [attr.aria-busy]="searching()">
    @if (searching()) { <div class="store-empty"><p>Searching products…</p></div> }
    @else if (searchError()) { <div class="store-empty" role="alert"><p>{{ searchError() }}</p><button type="button" class="store-button" (click)="loadProducts()">Try again</button></div> }
    @else if (!shop.products.length) { <div class="store-empty"><svg class="store-empty-icon" viewBox="0 0 80 64" fill="none" aria-hidden="true"><rect x="10" y="6" width="60" height="48" rx="8" stroke="currentColor" stroke-width="1.5"/><path d="M10 18h60M19 12h1m5 0h1m5 0h1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><text x="40" y="40" text-anchor="middle" fill="currentColor" font-family="inherit" font-size="17" letter-spacing="2">404</text></svg><h3>No products found</h3><p>{{ query() || category() ? 'Try another search or category.' : 'New products are on the way. Check back soon.' }}</p></div> }
    @else { <div class="store-grid">@for (product of shop.products; track product.id) { <article class="shop-product-card"><a [attr.href]="!shop.preview ? '/products/' + product.slug : null" [attr.aria-label]="'View ' + product.name" class="store-product-art" [style.--brand-tone]="tone()">@if (chosenVariant(product); as variant) { @if (!variant.stock) { <span class="product-card-badge sold-out">Sold out</span> } @else if (variant.offer_price !== null && variant.offer_price !== undefined) { <span class="product-card-badge">{{ discount(variant) }}% off</span> } }@if (product.images[0]; as image) { <img class="store-product-image" [src]="image.url" [alt]="product.name" [width]="image.width" [height]="image.height" loading="lazy" decoding="async"> } @else { <m-icon name="box" /><span class="store-caption">{{ product.name }}</span> }</a><div class="store-product-meta"><span class="store-caption">{{ product.category }}</span><h3><a [attr.href]="!shop.preview ? '/products/' + product.slug : null">{{ product.name }}</a></h3><div class="store-price">@if (priceRange(product); as range) { <p><span class="price-currency">{{ shop.currency }}</span> {{ range.low | number:priceDigits() }}@if (range.high !== range.low) { <span class="price-range-separator"> – </span>{{ range.high | number:priceDigits() }} }</p>@if (!product.has_variants && chosenVariant(product); as variant) { @if (variant.offer_price !== null && variant.offer_price !== undefined) { <del>{{ shop.currency }} {{ variant.price | number:priceDigits() }}</del> } } }</div>@if (shop.preview && product.status === 'draft') { <span class="draft-label">DRAFT · PREVIEW ONLY</span> }@if (!shop.preview) { <button type="button" class="store-button listing-add" [disabled]="!chosenVariant(product)?.stock" (click)="cart.add(product,chosenVariant(product))">{{ chosenVariant(product)?.stock ? 'Add to cart' : 'Out of stock' }}<m-icon name="bag" /></button> }</div></article> }</div> }
    </div>@if (!searching() && !searchError() && shop.has_more) { <div class="store-load-more"><button type="button" class="store-button" (click)="loadProducts(true)" [disabled]="loadingMore()">{{ loadingMore() ? 'Loading…' : 'Load more products' }}</button></div> }
    </section> }</main>
    <footer class="store-footer store-footer-details">
      <div class="footer-columns">
        @if (shop.settings.logo_url || shop.settings.description?.trim()) { <div class="footer-intro">@if (shop.settings.logo_url) { <a href="#top" [attr.aria-label]="shop.name + ' home'"><img class="footer-logo" [src]="shop.settings.logo_url" [alt]="shop.name" loading="lazy" decoding="async"></a> }@if (shop.settings.description?.trim()) { <div class="footer-description rich-content" [innerHTML]="shop.settings.description | richText"></div> }</div> }
        @if (shop.phone || shop.settings.contact_email || shop.settings.contact_address?.trim()) { <section class="footer-column" aria-labelledby="footer-contacts"><h2 id="footer-contacts">Contact</h2>@if (shop.phone) { <a class="footer-contact" [href]="phoneHref(shop.phone)"><m-icon name="phone" />{{ shop.phone }}</a> }@if (shop.settings.contact_email) { <a class="footer-contact" [href]="'mailto:' + shop.settings.contact_email"><m-icon name="mail" />{{ shop.settings.contact_email }}</a> }@if (shop.settings.contact_address?.trim()) { <p class="footer-address">{{ shop.settings.contact_address }}</p> }</section> }
        @if (socialLinks().length) { <section class="footer-column" aria-labelledby="footer-social"><h2 id="footer-social">Follow us</h2>@for (social of socialLinks(); track social.label) { <a class="footer-contact" [href]="social.url" target="_blank" rel="noopener noreferrer"><m-icon [name]="social.icon" />{{ social.label }} <span aria-hidden="true">↗</span></a> }</section> }
        @if (policies().length) { <section class="footer-column" aria-labelledby="footer-policies"><h2 id="footer-policies">Policies</h2>@for (policy of policies(); track policy.label) { <button type="button" (click)="selectedPolicy.set(policy); policyDialog.showModal()">{{ policy.label }}</button> }</section> }
      </div><div class="footer-bottom"><small>© {{ year }} {{ shop.name }}</small><a class="footer-powered-by" href="https://mshoppa.com" target="_blank" rel="noopener noreferrer">Powered by MSHOPPA</a></div>
    </footer>
    <dialog #policyDialog class="store-policy-dialog" aria-labelledby="policy-heading"><div class="policy-dialog-heading"><h2 id="policy-heading">{{ selectedPolicy()?.label }}</h2><button type="button" (click)="policyDialog.close()" aria-label="Close policy"><m-icon name="close" /></button></div><div class="policy-body rich-content" [innerHTML]="selectedPolicy()?.text | richText"></div></dialog>
    @if (whatsappHref(); as link) { <a class="store-whatsapp" [href]="link" target="_blank" rel="noopener noreferrer" [attr.aria-label]="'Chat with ' + shop.name + ' on WhatsApp'" title="Chat on WhatsApp"><svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M26.6 5.4A14 14 0 0 0 4.5 22L2.8 29l7.2-1.7A14 14 0 0 0 26.6 5.4Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="m11.1 9.1-1.5.1c-.5 0-1.6 1.6-1.4 3.1.4 4.1 6.1 9.5 10.4 9.9 1.6.1 3.1-1 3.3-1.6l.2-1.6-4-1.9-1.5 1.8c-2.6-1-4-2.4-5.1-4.9l1.6-1.6-2-3.3Z" fill="currentColor"/></svg></a> }
  } @else { <main class="store-unavailable"><span class="store-caption">MSHOPPA STOREFRONTS</span><h1>A good thing<br>is on its way.</h1><p>{{ error() }}</p><span class="store-caption">COME BACK SOON.</span></main> }
` })
class StorefrontRoot implements OnDestroy {
  api = inject(Api); store = signal<Store|null>(null); loading = signal(true); error = signal(''); year = new Date().getFullYear();
  category = signal(''); sort = signal('featured');
  mobileSearchOpen = signal(false); private changeDetector = inject(ChangeDetectorRef);
  openMobileSearch(input:HTMLInputElement) { this.mobileSearchOpen.set(true); this.changeDetector.detectChanges(); input.focus(); }
  closeMobileSearch(toggle:HTMLButtonElement) { this.mobileSearchOpen.set(false); if(this.query()) this.clearSearch(); this.changeDetector.detectChanges(); toggle.focus(); }
  chooseCategory(category:string) { this.category.set(category); this.scheduleSearch(); }
  changeSort(event:Event) { this.sort.set((event.target as HTMLSelectElement).value); this.scheduleSearch(); }
  query = signal(''); searching = signal(false); searchError = signal(''); loadingMore = signal(false);
  detailImage = signal(0); cart = inject(CartService); checkoutPage = /^\/checkout\/?$/.test(location.pathname);
  variantSelection = signal<Record<string,string>>({});
  chosenVariant(product:Product): Product['variants'][number] | undefined { const id = this.variantSelection()[product.id]; return product.variants.find(variant => variant.id === id) || product.variants.find(variant => (variant.stock ?? 0) > 0) || product.variants[0]; }
  chooseVariant(product:Product,event:Event) { const id = (event.target as HTMLSelectElement).value; this.variantSelection.update(values => ({...values,[product.id]:id})); }
  priceDigits() { return ['UGX','RWF'].includes(this.store()?.currency || '') ? '1.0-0' : '1.2-2'; }
  discount(variant:Product['variants'][number]) { return Math.round((1 - Number(variant.offer_price) / Number(variant.price)) * 100); }
  priceRange(product:Product) { if (!product.variants.length) return null; const prices=product.variants.map(v=>Number(v.offer_price ?? v.price)); return {low:Math.min(...prices),high:Math.max(...prices)}; }
  lowestVariant(product:Product) { return product.variants.reduce<Product['variants'][number] | undefined>((lowest, variant) => !lowest || Number(variant.offer_price ?? variant.price) < Number(lowest.offer_price ?? lowest.price) ? variant : lowest, undefined); }
  selectedPolicy = signal<{label:string;text:string}|null>(null);
  socialLinks() {
    const settings = this.store()?.settings;
    return SOCIAL_PROFILES.map(social => ({...social,url:settings?.[social.key]})).filter(item => !!item.url);
  }
  policies() {
    const settings = this.store()?.settings;
    return [{label:'Return / refund policy',text:settings?.return_refund_policy || ''},{label:'Privacy policy',text:settings?.privacy_policy || ''},{label:'Terms and conditions',text:settings?.terms_conditions || ''}].filter(item => !!item.text.trim());
  }
  whatsappHref(usePhoneFallback = false) { const raw = this.store()?.settings.whatsapp_number || (usePhoneFallback ? this.store()?.phone : '') || ''; const number = raw.replace(/[^0-9]/g, ''); return /^[1-9]\d{8,14}$/.test(number) ? `https://wa.me/${number}` : null; }
  private searchTimer?: ReturnType<typeof setTimeout>;
  private requestVersion = 0; private page = 1; private previewToken: string | null = null;
  search(event: Event) { this.query.set((event.target as HTMLInputElement).value); this.scheduleSearch(); }
  clearSearch() { this.query.set(''); this.scheduleSearch(); }
  private scheduleSearch() {
    clearTimeout(this.searchTimer); this.requestVersion++; this.searching.set(true); this.loadingMore.set(false); this.searchError.set('');
    this.searchTimer = setTimeout(() => void this.loadProducts(), 180);
  }
  async loadProducts(append = false) {
    const version = ++this.requestVersion, page = append ? this.page + 1 : 1;
    this.searchError.set(''); (append ? this.loadingMore : this.searching).set(true);
    try {
      const result = await this.api.get<Store>(`${this.previewToken ? 'storefront/preview/' : 'storefront/'}?q=${encodeURIComponent(this.query().trim())}&page=${page}&category=${encodeURIComponent(this.category())}&sort=${encodeURIComponent(this.sort())}`, this.previewToken ? {'X-Mshoppa-Preview':this.previewToken} : {});
      if (version !== this.requestVersion) return;
      this.store.update(current => ({...result, products:append ? [...new Map([...(current?.products ?? []),...result.products].map(product => [product.id, product])).values()] : result.products}));
      this.page = page;
    } catch(e) { if (version === this.requestVersion) this.searchError.set(errorMessage(e)); }
    finally { if (version === this.requestVersion) { this.searching.set(false); this.loadingMore.set(false); } }
  }
  ngOnDestroy() { clearTimeout(this.searchTimer); this.requestVersion++; }
  tones:Record<string,string> = {taupe:'#d1b0a4',sky:'#879aab',mauve:'#a57e75',olive:'#9e8949',cream:'#e0dacf'};
  tone() { return this.tones[this.store()?.settings.surface_tone || 'taupe']; }
  phoneHref(phone: string): string | null { const number = phone.replace(/[\s().-]/g, ''); return /^\+?\d{3,15}$/.test(number) ? `tel:${number}` : null; }
  constructor() { void this.load(); }
  async load() {
    const preview = new URLSearchParams(location.hash.slice(1)).get('preview');
    this.previewToken = preview;
    if (preview) history.replaceState(null, '', location.pathname);
    try {
      const match = location.pathname.match(/^\/products\/([^/]+)\/?$/);
      const productQuery = match ? `?product=${encodeURIComponent(decodeURIComponent(match[1]))}` : '';
      const shop = await this.api.get<Store>(match ? `storefront/${productQuery}` : preview ? 'storefront/preview/' : 'storefront/', !match && preview ? {'X-Mshoppa-Preview':preview} : {});
      this.cart.init(shop);
      this.store.set(shop);
      document.title = shop.product ? `${shop.product.name} — ${shop.name}` : shop.name;
    } catch(e) { this.error.set(location.pathname.startsWith('/products/') ? 'This product is not available. It may no longer be published, or the shop may be offline.' : preview ? errorMessage(e) : 'This store is not available yet. Please check the address or return later.'); } finally { this.loading.set(false); }
  }
}
bootstrapApplication(StorefrontRoot,{providers:[provideHttpClient()]}).catch(console.error);
