import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface GeocodeResult {
  latitude: number;
  longitude: number;
  displayName: string;
}

@Injectable({ providedIn: 'root' })
export class GeocodeApi {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = 'http://localhost:8080/api/geocode/search';

  search(query: string): Observable<GeocodeResult> {
    const params = new URLSearchParams({ query });
    return this.http.get<GeocodeResult>(`${this.apiUrl}?${params.toString()}`);
  }
}
