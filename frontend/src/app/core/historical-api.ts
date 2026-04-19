import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface HistoricalEvent {
  id: string;
  time: string;
  place: string;
  magnitude: number;
  latitude: number;
  longitude: number;
  depthKm: number;
}

export interface SeismicGap {
  centerLat: number;
  centerLon: number;
  latSpan: number;
  lonSpan: number;
  silentYears: number;
  magnitudeThreshold: number;
}

@Injectable({ providedIn: 'root' })
export class HistoricalApi {
  private readonly http = inject(HttpClient);
  private readonly base = 'http://localhost:8080/api/historical';

  events(years = 50, minMagnitude = 5.0): Observable<HistoricalEvent[]> {
    return this.http.get<HistoricalEvent[]>(`${this.base}/events?years=${years}&minMagnitude=${minMagnitude}`);
  }

  gaps(years = 50, gapMagnitude = 5.5, silentYears = 30, gridSize = 18): Observable<SeismicGap[]> {
    return this.http.get<SeismicGap[]>(
      `${this.base}/gaps?years=${years}&gapMagnitude=${gapMagnitude}&silentYears=${silentYears}&gridSize=${gridSize}`
    );
  }
}
