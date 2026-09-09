import { Injectable, inject, signal } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Api, Business, Page } from '@mshoppa/api';

export const requireSession: CanActivateFn = async () => {
  const api = inject(Api), router = inject(Router);
  try { return await api.me() ? true : router.createUrlTree(['/login']); }
  catch { return router.createUrlTree(['/login']); }
};

@Injectable({ providedIn: 'root' })
export class Workspace {
  private api = inject(Api);
  businesses = signal<Business[]>([]);
  selected = signal<Business | null>(null);
  async load() {
    const response = await this.api.get<Page<Business>>('businesses/');
    const businesses = [...response.results];
    for (let page = 2; businesses.length < response.count; page++) {
      const next = await this.api.get<Page<Business>>(`businesses/?page=${page}`);
      if (!next.results.length) break;
      businesses.push(...next.results);
    }
    this.businesses.set(businesses);
    const previous = this.selected();
    this.selected.set(businesses.find(b => b.id === previous?.id) || businesses[0] || null);
  }
  choose(id: string) { this.selected.set(this.businesses().find(b => b.id === id) || null); }
  publicStoreUrl(): string | null {
    const business = this.selected();
    return business?.published && !business.suspended && business.provisioning_status === 'ready' && business.storefront_url ? business.storefront_url : null;
  }
}
