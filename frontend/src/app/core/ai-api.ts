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

export interface GraphChatRequest {
  question: string;
  sessionId?: string;
  userContext?: { latitude?: number; longitude?: number; city?: string };
}

export interface GraphChatResponse {
  answer: string;
  category: 'data' | 'guide' | 'risk' | 'smalltalk';
  sources: string[];
}

export interface GraphQuakeDetailResponse {
  event: Record<string, unknown>;
  aftershocks: Record<string, unknown>[];
  similar: Record<string, unknown>[];
  depth: 'brief' | 'standard' | 'detailed' | string;
  summary: string;
  riskLevel: 'low' | 'moderate' | 'high' | 'critical' | string;
  recommendations: string[];
}

export interface GraphBuildingRiskRequest {
  building: {
    addressText?: string;
    constructionYear: number;
    floorCount: number;
    structuralSystem: string;
    soilType: string;
    columnCracks: boolean;
    pastDamage: boolean;
    softStorey: boolean;
    heavyTopFloor: boolean;
    irregularShape: boolean;
    retrofitDone: boolean;
  };
  location?: {
    latitude: number;
    longitude: number;
    label?: string;
    source?: string;
  } | null;
}

export interface GraphBuildingRiskResponse {
  totalScore: number;
  level: 'dusuk' | 'orta' | 'yuksek' | 'kritik' | string;
  label: string;
  confidence: string;
  componentScores: Record<string, number>;
  primaryDrivers: string[];
  buildingDrivers: string[];
  locationDrivers: string[];
  recommendedActions: string[];
  cautions: string[];
  summary: string;
  context: Record<string, unknown>;
  sources: string[];
}

@Injectable({ providedIn: 'root' })
export class AiApi {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = 'http://localhost:8080/api/ai/chat';
  private readonly graphChatUrl = 'http://localhost:8080/api/graph/chat';
  private readonly graphQuakeDetailUrl = 'http://localhost:8080/api/graph/quake-detail';
  private readonly graphBuildingRiskUrl = 'http://localhost:8080/api/graph/building-risk';

  chat(payload: AiChatRequest): Observable<AiChatResponse> {
    return this.http.post<AiChatResponse>(this.apiUrl, payload);
  }

  graphChat(payload: GraphChatRequest): Observable<GraphChatResponse> {
    return this.http.post<GraphChatResponse>(this.graphChatUrl, payload);
  }

  graphQuakeDetail(eventId: string): Observable<GraphQuakeDetailResponse> {
    return this.http.post<GraphQuakeDetailResponse>(this.graphQuakeDetailUrl, { eventId });
  }

  graphBuildingRisk(payload: GraphBuildingRiskRequest): Observable<GraphBuildingRiskResponse> {
    return this.http.post<GraphBuildingRiskResponse>(this.graphBuildingRiskUrl, payload);
  }

  streamGraphChat(
    payload: GraphChatRequest,
    handlers: {
      meta?: (meta: Pick<GraphChatResponse, 'category' | 'sources'>) => void;
      token: (token: string) => void;
      done: (response: GraphChatResponse) => void;
      error: () => void;
    }
  ): () => void {
    const params = new URLSearchParams({
      question: payload.question,
      sessionId: payload.sessionId || 'default',
    });
    if (payload.userContext?.latitude !== undefined && payload.userContext?.longitude !== undefined) {
      params.set('latitude', String(payload.userContext.latitude));
      params.set('longitude', String(payload.userContext.longitude));
    }
    const source = new EventSource(`http://localhost:8080/api/graph/chat/stream?${params.toString()}`);
    source.addEventListener('meta', (event) => {
      handlers.meta?.(JSON.parse((event as MessageEvent).data));
    });
    source.addEventListener('token', (event) => {
      handlers.token(JSON.parse((event as MessageEvent).data));
    });
    source.addEventListener('done', (event) => {
      handlers.done(JSON.parse((event as MessageEvent).data));
      source.close();
    });
    source.onerror = () => {
      handlers.error();
      source.close();
    };
    return () => source.close();
  }
}
