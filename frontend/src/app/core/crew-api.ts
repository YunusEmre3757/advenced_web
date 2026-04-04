import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface CrewAnalyzeRequest {
  eventId: string;
  location: string;
  magnitude: number;
  depthKm: number;
  latitude: number;
  longitude: number;
  hours?: number;
  minMagnitude?: number;
}

export interface CrewAnalyzeResult {
  hazardLevel: 'CRITICAL' | 'HIGH' | 'MODERATE' | 'LOW' | 'UNKNOWN';
  nearestFault: string;
  distanceKm: number;
  faultType: string;
  slipRate: string;
  soilClass: string;
  historicalSummary: string;
  seismicGapStatus: 'UZUN_SESSIZLIK' | 'YAKIN_KIRILMA' | 'DUZENLI_AKTIVITE' | 'BILINMIYOR';
  seismicGapNote: string;
  dataCollectorSummary: string;
  faultAnalystReport: string;
  riskAssessorReport: string;
  finalReport: string;
  reportDate: string;
  // error case
  error?: string;
  message?: string;
}

@Injectable({ providedIn: 'root' })
export class CrewApi {
  private readonly http = inject(HttpClient);
  // FastAPI crew service - direct connection
  private readonly baseUrl = 'http://localhost:8002';

  analyze(payload: CrewAnalyzeRequest): Observable<CrewAnalyzeResult> {
    return this.http.post<CrewAnalyzeResult>(`${this.baseUrl}/analyze`, payload);
  }

  health(): Observable<{ crewApiStatus: string; crewApiCode?: number }> {
    return this.http.get<{ crewApiStatus: string; crewApiCode?: number }>(`${this.baseUrl}/health`);
  }
}
