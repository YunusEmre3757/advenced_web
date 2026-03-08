import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface AiChatRequest {
  question: string;
  hours?: number;
  minMagnitude?: number;
  limit?: number;
  eventId?: string;
  latitude?: number;
  longitude?: number;
  bbox?: [number, number, number, number];
}

export interface AiChatResponse {
  answer: string;
  model: string;
  eventCount: number;
  focusEventId?: string | null;
  focusEventLocation?: string | null;
  focusEventMagnitude?: number | null;
  focusEventDepthKm?: number | null;
  nearestFaultDistanceKm?: number | null;
  nearestFaultSummary?: string | null;
  note?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AiApi {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = 'http://localhost:8080/api/ai/chat';

  chat(payload: AiChatRequest): Observable<AiChatResponse> {
    return this.http.post<AiChatResponse>(this.apiUrl, payload);
  }
}
