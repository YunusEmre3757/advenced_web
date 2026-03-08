import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface SoilZoneGeoJson {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry: {
      type: 'Polygon' | 'MultiPolygon';
      coordinates: unknown;
    };
    properties?: {
      siteClass?: string;
      vs30?: number;
      [key: string]: unknown;
    };
  }>;
}

@Injectable({ providedIn: 'root' })
export class SoilZoneApi {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = 'http://localhost:8080/api/soil-zones';

  getSoilZones(params?: { bbox?: [number, number, number, number] }): Observable<SoilZoneGeoJson> {
    const query = new URLSearchParams();
    if (params?.bbox) {
      query.set('bbox', params.bbox.join(','));
    }

    const suffix = query.toString();
    const url = suffix ? `${this.apiUrl}?${suffix}` : this.apiUrl;
    return this.http.get<SoilZoneGeoJson>(url);
  }
}
