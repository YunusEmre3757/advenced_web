import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import {
  FamilyMember,
  NotificationPreference,
  NotificationTestResult,
  PastExperience,
  ProfileApi,
  UserLocation,
} from '../../core/profile-api';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './profile.html',
  styleUrl: './profile.css',
})
export class Profile {
  private readonly fb = inject(FormBuilder);
  private readonly profile = inject(ProfileApi);

  readonly locations = signal<UserLocation[]>([]);
  readonly familyMembers = signal<FamilyMember[]>([]);
  readonly experiences = signal<PastExperience[]>([]);
  readonly notificationPreference = signal<NotificationPreference | null>(null);
  readonly testResult = signal<NotificationTestResult | null>(null);
  readonly loading = signal(true);
  readonly saving = signal<string | null>(null);
  readonly error = signal<string | null>(null);

  readonly locationForm = this.fb.nonNullable.group({
    label: ['Ev', [Validators.required, Validators.maxLength(80)]],
    city: [''],
    district: [''],
    latitude: [41.0082, [Validators.required, Validators.min(-90), Validators.max(90)]],
    longitude: [28.9784, [Validators.required, Validators.min(-180), Validators.max(180)]],
    radiusKm: [25, [Validators.required, Validators.min(1), Validators.max(500)]],
    primaryLocation: [true],
  });

  readonly familyForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(120)]],
    relationship: [''],
    phone: [''],
    email: ['', [Validators.email]],
    pushoverKey: [''],
    notifyEnabled: [true],
  });

  readonly experienceForm = this.fb.nonNullable.group({
    title: ['', [Validators.required, Validators.maxLength(140)]],
    eventDate: [''],
    location: [''],
    magnitude: [null as number | null, [Validators.min(0), Validators.max(10)]],
    emotionalImpact: [''],
    notes: [''],
  });

  readonly notificationForm = this.fb.nonNullable.group({
    pushoverEnabled: [false],
    pushoverUserKey: [''],
    minMagnitude: [3, [Validators.required, Validators.min(1), Validators.max(9)]],
    notifyFamilyMembers: [true],
    emailEnabled: [false],
    emailAddress: ['', [Validators.email]],
  });

  constructor() {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.profile.listLocations().subscribe({
      next: locations => this.locations.set(locations),
      error: () => this.error.set('Konumlar alinamadi. Oturumunu kontrol et.'),
    });
    this.profile.listFamilyMembers().subscribe({
      next: family => this.familyMembers.set(family),
      error: () => this.error.set('Aile listesi alinamadi.'),
    });
    this.profile.listPastExperiences().subscribe({
      next: experiences => {
        this.experiences.set(experiences);
      },
      error: () => {
        this.error.set('Gecmis deneyimler alinamadi.');
      },
    });
    this.profile.getNotificationPreference().subscribe({
      next: preference => {
        this.notificationPreference.set(preference);
        this.notificationForm.patchValue({
          pushoverEnabled: preference.pushoverEnabled,
          pushoverUserKey: preference.pushoverUserKey || '',
          minMagnitude: preference.minMagnitude,
          notifyFamilyMembers: preference.notifyFamilyMembers,
          emailEnabled: preference.emailEnabled,
          emailAddress: preference.emailAddress || '',
        });
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Bildirim ayarlari alinamadi.');
        this.loading.set(false);
      },
    });
  }

  addLocation(): void {
    if (this.locationForm.invalid) {
      this.locationForm.markAllAsTouched();
      return;
    }
    this.saving.set('location');
    this.profile.createLocation(this.locationForm.getRawValue()).subscribe({
      next: location => {
        this.locations.update(items => location.primaryLocation
          ? [location, ...items.map(item => ({ ...item, primaryLocation: false }))]
          : [...items, location]);
        this.saving.set(null);
      },
      error: () => this.failSave('Konum kaydedilemedi.'),
    });
  }

  addFamilyMember(): void {
    if (this.familyForm.invalid) {
      this.familyForm.markAllAsTouched();
      return;
    }
    this.saving.set('family');
    this.profile.createFamilyMember(this.familyForm.getRawValue()).subscribe({
      next: member => {
        this.familyMembers.update(items => [...items, member]);
        this.familyForm.reset({ name: '', relationship: '', phone: '', email: '', pushoverKey: '', notifyEnabled: true });
        this.saving.set(null);
      },
      error: () => this.failSave('Aile uyesi kaydedilemedi.'),
    });
  }

  addExperience(): void {
    if (this.experienceForm.invalid) {
      this.experienceForm.markAllAsTouched();
      return;
    }
    this.saving.set('experience');
    const raw = this.experienceForm.getRawValue();
    this.profile.createPastExperience({
      ...raw,
      eventDate: raw.eventDate || null,
      magnitude: raw.magnitude ?? null,
    }).subscribe({
      next: experience => {
        this.experiences.update(items => [experience, ...items]);
        this.experienceForm.reset({ title: '', eventDate: '', location: '', magnitude: null, emotionalImpact: '', notes: '' });
        this.saving.set(null);
      },
      error: () => this.failSave('Deneyim kaydedilemedi.'),
    });
  }

  canSendTest(): boolean {
    const form = this.notificationForm.controls;
    const pushoverReady = form.pushoverEnabled.value && !!form.pushoverUserKey.value;
    const emailReady = form.emailEnabled.value && !!form.emailAddress.value && form.emailAddress.valid;
    return pushoverReady || emailReady;
  }

  sendTestNotification(): void {
    this.saving.set('test');
    this.testResult.set(null);
    this.profile.sendTestNotification().subscribe({
      next: result => {
        this.testResult.set(result);
        this.saving.set(null);
      },
      error: err => {
        this.saving.set(null);
        const message = err?.error?.message || 'Test bildirimi gonderilemedi. Ayarlari kontrol et.';
        this.testResult.set({
          delivered: false,
          eventId: '',
          sentAt: new Date().toISOString(),
          results: [{ channel: 'ERROR', delivered: false, status: 'ERROR', message }],
        });
      },
    });
  }

  saveNotificationPreference(): void {
    if (this.notificationForm.invalid) {
      this.notificationForm.markAllAsTouched();
      return;
    }
    this.saving.set('notifications');
    const raw = this.notificationForm.getRawValue();
    this.profile.updateNotificationPreference({
      ...raw,
      pushoverUserKey: raw.pushoverUserKey || null,
      emailAddress: raw.emailAddress || null,
    }).subscribe({
      next: preference => {
        this.notificationPreference.set(preference);
        this.saving.set(null);
      },
      error: () => this.failSave('Bildirim ayarlari kaydedilemedi.'),
    });
  }

  deleteLocation(id: string): void {
    this.profile.deleteLocation(id).subscribe({
      next: () => this.locations.update(items => items.filter(item => item.id !== id)),
      error: () => this.error.set('Konum silinemedi.'),
    });
  }

  deleteFamilyMember(id: string): void {
    this.profile.deleteFamilyMember(id).subscribe({
      next: () => this.familyMembers.update(items => items.filter(item => item.id !== id)),
      error: () => this.error.set('Aile uyesi silinemedi.'),
    });
  }

  deleteExperience(id: string): void {
    this.profile.deletePastExperience(id).subscribe({
      next: () => this.experiences.update(items => items.filter(item => item.id !== id)),
      error: () => this.error.set('Deneyim silinemedi.'),
    });
  }

  private failSave(message: string): void {
    this.error.set(message);
    this.saving.set(null);
  }
}
