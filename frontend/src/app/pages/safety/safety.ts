import { Component, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import {
  FamilyFanoutResult,
  SafetyApi,
  SafetyCheckin,
  SafetyCheckinPayload,
  SafetyStatus,
} from '../../core/safety-api';

@Component({
  selector: 'app-safety',
  standalone: true,
  imports: [ReactiveFormsModule, DatePipe, DecimalPipe],
  templateUrl: './safety.html',
  styleUrl: './safety.css',
})
export class Safety {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(SafetyApi);

  readonly history = signal<SafetyCheckin[]>([]);
  readonly lastFanout = signal<FamilyFanoutResult[] | null>(null);
  readonly submitting = signal<SafetyStatus | null>(null);
  readonly error = signal<string | null>(null);
  readonly locating = signal(false);
  readonly locationCaptured = signal<{ lat: number; lng: number } | null>(null);

  readonly noteForm = this.fb.nonNullable.group({
    note: ['', [Validators.maxLength(500)]],
    eventId: [''],
  });

  constructor() {
    this.reload();
  }

  reload(): void {
    this.api.history().subscribe({
      next: rows => this.history.set(rows),
      error: () => this.error.set('Gecmis alinamadi. Oturumunu kontrol et.'),
    });
  }

  captureLocation(): void {
    if (!('geolocation' in navigator)) {
      this.error.set('Tarayici konum servisini desteklemiyor.');
      return;
    }
    this.locating.set(true);
    navigator.geolocation.getCurrentPosition(
      pos => {
        this.locationCaptured.set({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        this.locating.set(false);
      },
      () => {
        this.locating.set(false);
        this.error.set('Konum alinamadi. Tarayici izni verdiginden emin ol.');
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  send(status: SafetyStatus): void {
    this.submitting.set(status);
    this.error.set(null);
    this.lastFanout.set(null);
    const raw = this.noteForm.getRawValue();
    const loc = this.locationCaptured();
    const payload: SafetyCheckinPayload = {
      status,
      note: raw.note || null,
      eventId: raw.eventId || null,
      latitude: loc?.lat ?? null,
      longitude: loc?.lng ?? null,
    };
    this.api.checkIn(payload).subscribe({
      next: res => {
        this.history.update(h => [res.checkin, ...h]);
        this.lastFanout.set(res.familyNotifications);
        this.submitting.set(null);
      },
      error: () => {
        this.submitting.set(null);
        this.error.set('Durumun kaydedilemedi. Tekrar dene.');
      },
    });
  }

  statusLabel(status: SafetyStatus): string {
    return status === 'SAFE' ? 'Guvendeyim'
      : status === 'NEEDS_HELP' ? 'Yardim lazim'
      : 'Bilinmiyor';
  }
}
