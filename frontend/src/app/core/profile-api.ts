import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export interface UserLocation {
  id: string;
  label: string;
  city: string | null;
  district: string | null;
  latitude: number;
  longitude: number;
  radiusKm: number;
  primaryLocation: boolean;
}

export interface LocationPayload {
  label: string;
  city?: string | null;
  district?: string | null;
  latitude: number;
  longitude: number;
  radiusKm: number;
  primaryLocation: boolean;
}

export interface FamilyMember {
  id: string;
  name: string;
  relationship: string | null;
  phone: string | null;
  email: string | null;
  pushoverKey: string | null;
  notifyEnabled: boolean;
}

export interface FamilyMemberPayload {
  name: string;
  relationship?: string | null;
  phone?: string | null;
  email?: string | null;
  pushoverKey?: string | null;
  notifyEnabled: boolean;
}

export interface PastExperience {
  id: string;
  title: string;
  eventDate: string | null;
  location: string | null;
  magnitude: number | null;
  emotionalImpact: string | null;
  notes: string | null;
}

export interface PastExperiencePayload {
  title: string;
  eventDate?: string | null;
  location?: string | null;
  magnitude?: number | null;
  emotionalImpact?: string | null;
  notes?: string | null;
}

export interface NotificationPreference {
  id: string;
  pushoverEnabled: boolean;
  pushoverUserKey: string | null;
  minMagnitude: number;
  notifyFamilyMembers: boolean;
  emailEnabled: boolean;
  emailAddress: string | null;
}

export interface NotificationPreferencePayload {
  pushoverEnabled: boolean;
  pushoverUserKey?: string | null;
  minMagnitude: number;
  notifyFamilyMembers: boolean;
  emailEnabled: boolean;
  emailAddress?: string | null;
}

export interface NotificationChannelResult {
  channel: string;
  delivered: boolean;
  status: string;
  message: string;
}

export interface NotificationTestResult {
  delivered: boolean;
  eventId: string;
  sentAt: string;
  results: NotificationChannelResult[];
}

@Injectable({ providedIn: 'root' })
export class ProfileApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = 'http://localhost:8080/api/profile';

  listLocations(): Observable<UserLocation[]> {
    return this.http.get<UserLocation[]>(`${this.baseUrl}/locations`);
  }

  createLocation(payload: LocationPayload): Observable<UserLocation> {
    return this.http.post<UserLocation>(`${this.baseUrl}/locations`, payload);
  }

  deleteLocation(id: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/locations/${id}`);
  }

  listFamilyMembers(): Observable<FamilyMember[]> {
    return this.http.get<FamilyMember[]>(`${this.baseUrl}/family-members`);
  }

  createFamilyMember(payload: FamilyMemberPayload): Observable<FamilyMember> {
    return this.http.post<FamilyMember>(`${this.baseUrl}/family-members`, payload);
  }

  deleteFamilyMember(id: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/family-members/${id}`);
  }

  listPastExperiences(): Observable<PastExperience[]> {
    return this.http.get<PastExperience[]>(`${this.baseUrl}/past-experiences`);
  }

  createPastExperience(payload: PastExperiencePayload): Observable<PastExperience> {
    return this.http.post<PastExperience>(`${this.baseUrl}/past-experiences`, payload);
  }

  deletePastExperience(id: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/past-experiences/${id}`);
  }

  getNotificationPreference(): Observable<NotificationPreference> {
    return this.http.get<NotificationPreference>(`${this.baseUrl}/notification-preferences`);
  }

  updateNotificationPreference(payload: NotificationPreferencePayload): Observable<NotificationPreference> {
    return this.http.put<NotificationPreference>(`${this.baseUrl}/notification-preferences`, payload);
  }

  sendTestNotification(): Observable<NotificationTestResult> {
    return this.http.post<NotificationTestResult>(
      'http://localhost:8080/api/notifications/test', {}
    );
  }
}
