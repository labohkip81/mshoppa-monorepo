import { Component, ElementRef, inject, OnDestroy, signal, ViewChild } from '@angular/core';
import { CurrencyPipe, TitleCasePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Api, errorMessage, Page, Product } from '@mshoppa/api';
import { Button, Icon } from './index';
import { Workspace } from './session';
import { RichTextEditor } from './rich-text';

interface ProductForm {
  name: string; category: string; description: string; status: 'draft' | 'published';
  price: number | string | null; offer_price: number | string | null; stock: number | null;
  has_variants: boolean; variants: VariantForm[];
}
interface VariantForm { key:number; id?:string; label:string; price:number|string|null; offer_price:number|string|null; stock:number|null }
interface PendingImage { file: File; url: string; key: number }

@Component({ standalone: true, imports: [FormsModule, RouterLink, CurrencyPipe, TitleCasePipe, Button, Icon, RichTextEditor], templateUrl: './products.html' })
export class ProductsPage implements OnDestroy {
  api = inject(Api); workspace = inject(Workspace);
  products = signal<Product[]>([]); count = signal(0); hasNext = signal(false);
  editorOpen = signal(false); current = signal<Product | null>(null);
  pendingImages = signal<PendingImage[]>([]); removedImages = signal<string[]>([]);
  dragging = signal(false); previewIndex = signal(0);
  @ViewChild('imagePreview') imagePreview?: ElementRef<HTMLDialogElement>;
  loading = signal(true); busy = signal(false); editorLoading = signal(false);
  error = signal(''); message = signal(''); progress = signal('');
  search = ''; page = 1; private imageSequence = 0; private loadSequence = 0; private variantSequence = 0;
  form: ProductForm = this.emptyForm();

  constructor() { void this.init(); }
  ngOnDestroy() { this.clearFiles(); }
  emptyForm(): ProductForm { return { name:'', category:'', description:'', status:'draft', price:null, offer_price:null, stock:0, has_variants:false, variants:[] }; }
  setVariantMode(enabled: boolean) {
    this.form.has_variants = enabled;
    if (enabled && !this.form.variants.length) {
      this.form.variants.push({key:++this.variantSequence, id:this.current()?.variants[0]?.id, label:'', price:this.form.price, offer_price:this.form.offer_price, stock:this.form.stock});
    } else if (!enabled && this.form.variants[0]) {
      const first = this.form.variants[0];
      this.form.price = first.price; this.form.offer_price = first.offer_price; this.form.stock = first.stock;
    }
  }
  addVariant() { if (this.form.variants.length < 50) this.form.variants.push({key:++this.variantSequence,label:'',price:null,offer_price:null,stock:0}); }
  removeVariant(key:number) { this.form.variants = this.form.variants.filter(variant => variant.key !== key); }
  totalStock(product:Product) { return product.variants.reduce((total, variant) => total + (variant.stock ?? 0), 0); }
  lowestVariant(product:Product) { return product.variants.reduce<Product['variants'][number] | undefined>((lowest, variant) => !lowest || Number(variant.offer_price ?? variant.price) < Number(lowest.offer_price ?? lowest.price) ? variant : lowest, undefined); }
  canWrite() { const business = this.workspace.selected(); return !!business && ['owner','manager'].includes(business.role) && !business.suspended; }
  productUrl(product: Product): string | null { const storeUrl = this.workspace.publicStoreUrl(); return product.status === 'published' && storeUrl ? `${storeUrl}/products/${encodeURIComponent(product.slug)}` : null; }
  currencyStep() { return ['UGX','RWF'].includes(this.workspace.selected()?.currency || '') ? '1' : '0.01'; }
  visibleImages() { return (this.current()?.images || []).filter(image => !this.removedImages().includes(image.id)); }
  imageCount() { return this.visibleImages().length + this.pendingImages().length; }
  previewImages() { return [...this.visibleImages().map(image => ({url:image.url, name:image.original_name})), ...this.pendingImages().map(image => ({url:image.url, name:image.file.name}))]; }
  openPreview(url: string) { this.previewIndex.set(Math.max(0, this.previewImages().findIndex(image => image.url === url))); this.imagePreview?.nativeElement.showModal(); }
  movePreview(delta: number) { this.previewIndex.update(index => (index + delta + this.previewImages().length) % this.previewImages().length); }
  closePreview() { this.imagePreview?.nativeElement.close(); }
  endpoint() { return `businesses/${this.workspace.selected()!.id}/products/`; }
  async init() { try { await this.workspace.load(); await this.load(); } catch(e) { this.error.set(errorMessage(e)); this.loading.set(false); } }
  clearFiles() { for (const image of this.pendingImages()) URL.revokeObjectURL(image.url); this.pendingImages.set([]); }
  resetEditor() { this.clearFiles(); this.current.set(null); this.removedImages.set([]); this.form = this.emptyForm(); this.progress.set(''); }
  add() { if (this.busy()) return; this.resetEditor(); this.error.set(''); this.message.set(''); this.editorOpen.set(true); }
  closeEditor() { if (this.busy()) return; this.resetEditor(); this.editorOpen.set(false); }
  async edit(product: Product) {
    if (this.busy()) return;
    this.resetEditor(); this.editorOpen.set(true); this.editorLoading.set(true); this.busy.set(true); this.error.set(''); this.message.set('');
    try {
      const latest = await this.api.get<Product>(`${this.endpoint()}${product.id}/`);
      this.current.set(latest);
      const variant = latest.variants[0];
      this.form = {name:latest.name, category:latest.category || '', description:latest.description || '', status:latest.status || 'draft', price:variant?.price ?? null, offer_price:variant?.offer_price ?? null, stock:variant?.stock ?? 0, has_variants:!!latest.has_variants, variants:latest.has_variants ? latest.variants.map(row => ({key:++this.variantSequence,id:row.id,label:row.label || '',price:row.price,offer_price:row.offer_price ?? null,stock:row.stock ?? 0})) : []};
    } catch(e) { this.error.set(errorMessage(e)); this.editorOpen.set(false); }
    finally { this.editorLoading.set(false); this.busy.set(false); }
  }
  switchStore(id: string) { if (this.busy()) return; this.workspace.choose(id); this.closeEditor(); this.page = 1; this.message.set(''); void this.load(); }
  searchProducts() { this.page = 1; void this.load(); }
  goPage(delta: number) { this.page += delta; void this.load(); }
  async load() {
    const sequence = ++this.loadSequence;
    this.loading.set(true); this.products.set([]);
    try {
      if (!this.workspace.selected()) { this.count.set(0); return; }
      const result = await this.api.get<Page<Product>>(`${this.endpoint()}?page=${this.page}&search=${encodeURIComponent(this.search)}`);
      if (sequence !== this.loadSequence) return;
      this.products.set(result.results); this.count.set(result.count); this.hasNext.set(!!result.next);
    } catch(e) { if (sequence === this.loadSequence) this.error.set(errorMessage(e)); }
    finally { if (sequence === this.loadSequence) this.loading.set(false); }
  }
  chooseImages(event: Event) {
    const input = event.target as HTMLInputElement;
    this.addImages(Array.from(input.files || []));
    input.value = '';
  }
  dropImages(event: DragEvent) { event.preventDefault(); this.dragging.set(false); if (!this.busy()) this.addImages(Array.from(event.dataTransfer?.files || [])); }
  dragOver(event: DragEvent) { event.preventDefault(); if (!this.busy()) this.dragging.set(true); }
  addImages(files: File[]) {
    const errors: string[] = [];
    for (const file of files) {
      if (this.imageCount() >= 8) { errors.push('A product can have up to 8 images.'); break; }
      if (file.size > 5 * 1024 * 1024) { errors.push(`${file.name}: maximum size is 5 MB.`); continue; }
      if (!['image/jpeg','image/png','image/webp'].includes(file.type) && !(file.type === '' && /\.(jpe?g|png|webp)$/i.test(file.name))) { errors.push(`${file.name}: choose JPEG, PNG or WebP.`); continue; }
      this.pendingImages.update(images => [...images, {file, url:URL.createObjectURL(file), key:++this.imageSequence}]);
    }
    this.error.set(errors.join(' '));
  }
  removePending(key: number) {
    const image = this.pendingImages().find(item => item.key === key);
    if (image) URL.revokeObjectURL(image.url);
    this.pendingImages.update(images => images.filter(item => item.key !== key));
  }
  removeExisting(id: string) { this.removedImages.update(ids => [...ids, id]); }
  async save() {
    if (this.busy()) return;
    this.error.set(''); this.message.set(''); this.busy.set(true); this.progress.set('Saving product…');
    let detailsSaved = false;
    const wasEditing = !!this.current();
    try {
      const {variants, price, offer_price, stock, ...fields} = this.form;
      const data = fields.has_variants ? {...fields, variants:variants.map(({key,...row}) => ({...row,offer_price:row.offer_price === '' ? null : row.offer_price,stock:row.stock ?? 0}))} : {...fields,price,offer_price:offer_price === '' ? null : offer_price,stock};
      const current = this.current();
      const saved = await this.api.send<Product>(current ? 'PATCH' : 'POST', current ? `${this.endpoint()}${current.id}/` : this.endpoint(), data);
      this.current.set(saved); detailsSaved = true;
      if (saved.has_variants) this.form.variants = this.form.variants.map((row, index) => ({...row,id:saved.variants[index]?.id}));
      // Metadata and each image are independent durable operations; retry never creates a second product.
      for (const id of [...this.removedImages()]) {
        this.progress.set('Updating images…');
        await this.api.send('DELETE', `${this.endpoint()}${saved.id}/images/${id}/`);
        this.current.update(product => product ? {...product, images:product.images.filter(image => image.id !== id)} : null);
        this.removedImages.update(ids => ids.filter(value => value !== id));
      }
      const pending = [...this.pendingImages()];
      for (const [index, image] of pending.entries()) {
        this.progress.set(`Uploading image ${index + 1} of ${pending.length}…`);
        const form = new FormData(); form.append('image', image.file);
        const uploaded = await this.api.send<Product['images'][number]>('POST', `${this.endpoint()}${saved.id}/images/`, form);
        this.current.update(product => product ? {...product, images:[...product.images, uploaded]} : null);
        this.removePending(image.key);
      }
      this.editorOpen.set(false); this.resetEditor(); this.search = ''; this.page = 1;
      this.message.set(wasEditing ? 'Product changes saved.' : saved.status === 'published' ? 'Product saved and visible on your online store.' : 'Product saved as a draft.');
      await this.load();
    } catch(e) {
      this.error.set((detailsSaved ? 'Product details were saved, but some image changes could not be completed. Your remaining changes are still here; save again to retry. ' : '') + errorMessage(e));
    } finally { this.busy.set(false); this.progress.set(''); }
  }
}
