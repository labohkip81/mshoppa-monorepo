import { Injectable, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import type { components } from './schema';

export type User = components['schemas']['User'];
export type Business = components['schemas']['Business'];
export type Application = components['schemas']['Application'];
export type Product = components['schemas']['Product'];
export type StoreSettings = components['schemas']['Settings'];
export interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }

@Injectable({ providedIn: 'root' })
export class Api {
  readonly user = signal<User | null>(null);
  constructor(private http: HttpClient) {}
  get<T>(path: string, headers: Record<string,string> = {}): Promise<T> { return firstValueFrom(this.http.get<T>('/api/' + path, { headers })); }
  async send<T>(method: 'POST' | 'PATCH' | 'DELETE', path: string, body: unknown = {}): Promise<T> {
    // Fetch a current token for every mutation, including after login rotates it.
    const csrf = await this.get<{ token: string }>('auth/csrf/');
    return firstValueFrom(this.http.request<T>(method, '/api/' + path, { body, headers: { 'X-CSRFToken': csrf.token } }));
  }
  async me(): Promise<User | null> {
    try { const user = await this.get<User>('auth/me/'); this.user.set(user); return user; }
    catch (error) {
      if (error instanceof HttpErrorResponse && [401, 403].includes(error.status)) { this.user.set(null); return null; }
      throw error;
    }
  }
  async logout(): Promise<void> { await this.send('POST', 'auth/logout/'); this.user.set(null); }
}

export function errorMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    if (!error.status) return 'We could not reach the server. Please check your connection and try again.';
    if (error.status >= 500) return 'Something went wrong on the server. Please try again shortly.';
    const flatten = (value: unknown): string => typeof value === 'string' ? value : Array.isArray(value) ? value.map(flatten).join(' ') : value && typeof value === 'object' ? Object.entries(value).map(([key, val]) => `${['detail', 'non_field_errors'].includes(key) ? '' : key.replaceAll('_', ' ') + ': '}${flatten(val)}`).join(' ') : '';
    return flatten(error.error) || 'This request could not be completed.';
  }
  return 'Something went wrong. Please try again.';
}
