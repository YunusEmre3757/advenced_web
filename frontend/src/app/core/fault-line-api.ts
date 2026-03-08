import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface FaultLineGeoJson {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry: {
      type: 'LineString' | 'MultiLineString';
      coordinates: unknown;
    };
    properties?: Record<string, unknown>;
  }>;
}

@Injectable({ providedIn: 'root' })
export class FaultLineApi {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = 'http://localhost:8080/api/fault-lines';

  getFaultLines(params?: { bbox?: [number, number, number, number]; simplify?: number }): Observable<FaultLineGeoJson> {
    const query = new URLSearchParams();
    if (params?.bbox) {
      query.set('bbox', params.bbox.join(','));
    }
    if (typeof params?.simplify === 'number') {
      query.set('simplify', params.simplify.toString());
    }

    const suffix = query.toString();
    const url = suffix ? `${this.apiUrl}?${suffix}` : this.apiUrl;
    return this.http.get<FaultLineGeoJson>(url);
  }
}
