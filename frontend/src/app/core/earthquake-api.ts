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

export interface EarthquakeFeedSnapshot {
  source: string;
  emittedAt: string;
  intervalSeconds: number;
  earthquakes: EarthquakeApiItem[];
}

export interface HistoricalMatchApiItem {
  id: string;
  time: string;
  place: string;
  magnitude: number;
  latitude: number;
  longitude: number;
  depthKm: number;
  distanceKm: number;
  magnitudeDelta: number;
}

export interface HistoricalMatch {
  id: string;
  date: Date;
  place: string;
  magnitude: number;
  latitude: number;
  longitude: number;
  depthKm: number;
  distanceKm: number;
  magnitudeDelta: number;
}

export interface DyfiSummary {
  responses: number | null;
  maxCdi: number | null;
  url: string | null;
}

export interface EarthquakeDetailApiItem {
  event: EarthquakeApiItem;
  aftershocks: EarthquakeApiItem[];
  similarHistorical: HistoricalMatchApiItem[];
  dyfi: DyfiSummary | null;
}

export interface EarthquakeDetail {
  event: Earthquake;
  aftershocks: Earthquake[];
  similarHistorical: HistoricalMatch[];
  dyfi: DyfiSummary | null;
}

@Injectable({ providedIn: 'root' })
export class EarthquakeApi {
  private readonly http = inject(HttpClient);
  private readonly apiBase = 'http://localhost:8080/api/earthquakes';
  private readonly feedBase = 'http://localhost:8080/api/feed/earthquakes';
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

  getDetail(id: string, aftershockLimit = 16, similarLimit = 10): Observable<EarthquakeDetail> {
    return this.http.get<EarthquakeDetailApiItem>(
      `${this.apiBase}/${encodeURIComponent(id)}?aftershockLimit=${aftershockLimit}&similarLimit=${similarLimit}`
    ).pipe(
      map((row) => ({
        event: this.toEarthquake(row.event),
        aftershocks: this.toEarthquakes(row.aftershocks),
        similarHistorical: row.similarHistorical.map((item) => ({
          ...item,
          date: new Date(item.time)
        })),
        dyfi: row.dyfi
      }))
    );
  }

  streamRecent(
    handlers: {
      next: (earthquakes: Earthquake[], snapshot: EarthquakeFeedSnapshot) => void;
      error?: () => void;
      open?: () => void;
    },
    hours = 168,
    minMagnitude = 1,
    limit = 500
  ): () => void {
    const url = `${this.feedBase}/stream?hours=${hours}&minMagnitude=${minMagnitude}&limit=${limit}`;
    const source = new EventSource(url);

    source.onopen = () => handlers.open?.();
    source.onerror = () => handlers.error?.();
    source.addEventListener('snapshot', (event) => {
      const snapshot = JSON.parse((event as MessageEvent).data) as EarthquakeFeedSnapshot;
      handlers.next(snapshot.earthquakes.map((row) => this.toEarthquake(row)), snapshot);
    });

    return () => source.close();
  }

  toEarthquake(row: EarthquakeApiItem): Earthquake {
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

  toEarthquakes(rows: EarthquakeApiItem[]): Earthquake[] {
    return rows.map((row) => this.toEarthquake(row));
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
