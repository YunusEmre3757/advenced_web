import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type SafetyStatus = 'SAFE' | 'NEEDS_HELP' | 'UNKNOWN';

export interface SafetyCheckin {
  id: string;
  status: SafetyStatus;
  eventId: string | null;
  note: string | null;
  latitude: number | null;
  longitude: number | null;
  createdAt: string;
}

export interface FamilyFanoutResult {
  recipientLabel: string;
  channel: string;
  status: string;
  message: string;
}

export interface SafetyCheckinResponse {
  checkin: SafetyCheckin;
  familyNotifications: FamilyFanoutResult[];
}

export interface SafetyCheckinPayload {
  status: SafetyStatus;
  eventId?: string | null;
  note?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

@Injectable({ providedIn: 'root' })
export class SafetyApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = 'http://localhost:8080/api/safety';

  checkIn(payload: SafetyCheckinPayload): Observable<SafetyCheckinResponse> {
    return this.http.post<SafetyCheckinResponse>(`${this.baseUrl}/check-in`, payload);
  }

  history(): Observable<SafetyCheckin[]> {
    return this.http.get<SafetyCheckin[]>(`${this.baseUrl}/history`);
  }
}
