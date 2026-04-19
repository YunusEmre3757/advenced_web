import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ExposureEstimate {
  latitude: number;
  longitude: number;
  magnitude: number;
  depthKm: number;
  radiusKm: number;
  estimatedAffectedPopulation: number;
  exposedPopulationWithinRadius: number;
  cellsUsed: number;
  confidence: 'dusuk' | 'orta' | string;
  source: string;
  method: string;
}

@Injectable({ providedIn: 'root' })
export class ExposureApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = 'http://localhost:8080/api/exposure';

  estimate(latitude: number, longitude: number, magnitude: number, depthKm: number): Observable<ExposureEstimate> {
    const params = new URLSearchParams({
      latitude: String(latitude),
      longitude: String(longitude),
      magnitude: String(magnitude),
      depthKm: String(depthKm),
    });
    return this.http.get<ExposureEstimate>(`${this.baseUrl}/estimate?${params.toString()}`);
  }
}
