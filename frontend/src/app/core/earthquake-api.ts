import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { map, Observable } from 'rxjs';

export interface EarthquakeApiItem {
  id: string;
  time: string;
  location: string;
  latitude: number;
  longitude: number;
  magnitude: number;
  depthKm: number;
}

export interface Earthquake {
  id: string;
  date: Date;
  location: string;
  lat: number;
  lng: number;
  mag: number;
  depth: number;
  distanceKm: number;
}

@Injectable({ providedIn: 'root' })
export class EarthquakeApi {
  private readonly http = inject(HttpClient);
  private readonly apiBase = 'http://localhost:8080/api/earthquakes';
  // Ankara city center is used as a simple reference point for distance KPIs.
  private readonly anchorLat = 39.9334;
  private readonly anchorLng = 32.8597;

  getRecent(hours = 24, minMagnitude = 1, limit = 200): Observable<Earthquake[]> {
    return this.http.get<EarthquakeApiItem[]>(
      `${this.apiBase}/recent?hours=${hours}&minMagnitude=${minMagnitude}&limit=${limit}`
    ).pipe(
      map((rows) => rows.map((row) => this.toEarthquake(row)))
    );
  }

  private toEarthquake(row: EarthquakeApiItem): Earthquake {
    return {
      id: row.id,
      date: new Date(row.time),
      location: row.location,
      lat: row.latitude,
      lng: row.longitude,
      mag: row.magnitude,
      depth: row.depthKm,
      distanceKm: Math.round(this.haversineKm(this.anchorLat, this.anchorLng, row.latitude, row.longitude))
    };
  }

  private haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const toRad = (value: number) => value * Math.PI / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return 6371 * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
  }
}
