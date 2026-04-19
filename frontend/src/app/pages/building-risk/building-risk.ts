import {
  AfterViewInit,
  Component,
  ElementRef,
  OnDestroy,
  ViewChild,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { animate, style, transition, trigger } from '@angular/animations';
import * as L from 'leaflet';
import { AiApi, GraphBuildingRiskResponse } from '../../core/ai-api';
import { SoilZoneApi, SoilZoneGeoJson } from '../../core/soil-zone-api';
import { GeocodeApi } from '../../core/geocode-api';

interface RiskResult {
  totalScore: number;
  level: 'dusuk' | 'orta' | 'yuksek' | 'kritik';
  label: string;
  color: string;
  confidence: string;
  summary: string;
  primaryDrivers: string[];
  buildingDrivers: string[];
  locationDrivers: string[];
  recommendedActions: string[];
  cautions: string[];
  componentScores: Record<string, number>;
  context: Record<string, unknown>;
  sources: string[];
}

interface SelectedLocation {
  lat: number;
  lng: number;
  source: 'address' | 'device';
  label?: string;
}

const CIRCLE_CIRCUMFERENCE = 2 * Math.PI * 52; // r=52

@Component({
  selector: 'app-building-risk',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './building-risk.html',
  styleUrl: './building-risk.css',
  animations: [
    trigger('fadeSlide', [
      transition(':enter', [
        style({ opacity: 0, transform: 'translateY(16px)' }),
        animate('300ms ease-out', style({ opacity: 1, transform: 'translateY(0)' })),
      ]),
      transition(':leave', [
        animate('200ms ease-in', style({ opacity: 0, transform: 'translateY(-8px)' })),
      ]),
    ]),
  ],
})
export class BuildingRisk implements AfterViewInit, OnDestroy {
  @ViewChild('riskMap', { static: false }) riskMapEl!: ElementRef<HTMLDivElement>;

  private readonly fb = inject(FormBuilder);
  private readonly api = inject(AiApi);
  private readonly soilApi = inject(SoilZoneApi);
  private readonly geocodeApi = inject(GeocodeApi);

  private map?: L.Map;
  private readonly selectionLayer = L.layerGroup();
  private scoreAnimationFrame?: number;

  readonly currentStep = signal<number>(1);

  readonly steps = [
    { id: 1, label: 'Konum', icon: 'fa-solid fa-location-dot' },
    { id: 2, label: 'Bina', icon: 'fa-solid fa-building' },
    { id: 3, label: 'Durum', icon: 'fa-solid fa-eye' },
  ];

  readonly addressCtrl = new FormControl('', { nonNullable: true });

  readonly form = this.fb.nonNullable.group({
    addressText: [''],
    constructionYear: [2005, [Validators.required, Validators.min(1900), Validators.max(2025)]],
    floorCount: [4, [Validators.required, Validators.min(1), Validators.max(50)]],
    structuralSystem: ['reinforced_concrete', [Validators.required]],
    soilType: ['ZC', [Validators.required]],
    columnCracks: [false],
    pastDamage: [false],
    softStorey: [false],
    heavyTopFloor: [false],
    irregularShape: [false],
    retrofitDone: [false],
  });

  readonly result = signal<RiskResult | null>(null);
  readonly scoreLoading = signal(false);
  readonly scoreError = signal<string | null>(null);
  readonly selectedLocation = signal<SelectedLocation | null>(null);
  readonly locationError = signal<string | null>(null);
  readonly geocodeLoading = signal(false);
  readonly geocodeError = signal<string | null>(null);
  readonly soilLoading = signal(false);
  readonly soilHint = signal<string | null>(null);
  readonly soilError = signal<string | null>(null);
  readonly displayScore = signal<number>(0);

  readonly soilOptions = [
    { value: 'ZA', label: 'ZA - Sağlam kaya' },
    { value: 'ZB', label: 'ZB - Orta sağlam kaya' },
    { value: 'ZC', label: 'ZC - Çok sıkılaşmış zemin' },
    { value: 'ZD', label: 'ZD - Orta sıkı zemin' },
    { value: 'ZE', label: 'ZE - Gevşek / yumuşak zemin' },
    { value: 'ZF', label: 'ZF - Özel zemin (riskli)' },
  ];

  readonly structuralSystemOptions = [
    { value: 'reinforced_concrete', label: 'Betonarme' },
    { value: 'masonry', label: 'Yığma / taşıyıcı duvar' },
    { value: 'steel', label: 'Çelik' },
    { value: 'unknown', label: 'Bilinmiyor' },
  ];

  readonly scorePercent = computed(() => this.result()?.totalScore ?? 0);

  readonly locationLabel = computed(() => {
    const loc = this.selectedLocation();
    if (!loc) return 'Konum seçilmedi';
    if (loc.label) return loc.label;
    return `${loc.lat.toFixed(5)}, ${loc.lng.toFixed(5)} (${loc.source === 'device' ? 'cihaz konumu' : 'adres araması'})`;
  });

  readonly scoreDashOffset = computed(() => {
    const score = this.displayScore();
    const fraction = Math.min(score / 100, 1);
    return CIRCLE_CIRCUMFERENCE * (1 - fraction);
  });

  readonly componentCards = computed(() => {
    const s = this.result()?.componentScores ?? {};
    return [
      { key: 'structural', label: 'Yapısal', max: 35, value: s['structural'] ?? 0, icon: 'fa-solid fa-building' },
      { key: 'soil', label: 'Zemin', max: 15, value: s['soil'] ?? 0, icon: 'fa-solid fa-mountain' },
      { key: 'faultProximity', label: 'Fay Yakınlığı', max: 15, value: s['faultProximity'] ?? 0, icon: 'fa-solid fa-wave-square' },
      { key: 'historicalSeismicity', label: 'Tarihsel Sismik', max: 15, value: s['historicalSeismicity'] ?? 0, icon: 'fa-solid fa-chart-line' },
      { key: 'observedDamage', label: 'Gözlenen Hasar', max: 20, value: s['observedDamage'] ?? 0, icon: 'fa-solid fa-house-crack' },
    ];
  });

  ngAfterViewInit(): void {
    this.initMap();
  }

  ngOnDestroy(): void {
    if (this.map) this.map.remove();
    if (this.scoreAnimationFrame) cancelAnimationFrame(this.scoreAnimationFrame);
  }

  goToStep(n: number): void {
    this.currentStep.set(n);
    if (n === 1) {
      window.setTimeout(() => this.map?.invalidateSize(), 150);
    }
  }

  toggleCheck(field: string): void {
    const ctrl = this.form.get(field);
    if (ctrl) ctrl.setValue(!ctrl.value);
  }

  levelIcon(level: string): string {
    switch (level) {
      case 'dusuk': return 'fa-solid fa-circle-check';
      case 'orta': return 'fa-solid fa-circle-exclamation';
      case 'yuksek': return 'fa-solid fa-triangle-exclamation';
      case 'kritik': return 'fa-solid fa-skull-crossbones';
      default: return 'fa-solid fa-circle-question';
    }
  }

  resetWizard(): void {
    this.result.set(null);
    this.scoreError.set(null);
    this.displayScore.set(0);
    if (this.scoreAnimationFrame) cancelAnimationFrame(this.scoreAnimationFrame);
    this.currentStep.set(1);
    window.setTimeout(() => this.map?.invalidateSize(), 150);
  }

  submitAssessment(): void {
    this.scoreError.set(null);
    this.result.set(null);
    this.scoreLoading.set(true);

    const values = this.form.getRawValue();
    const location = this.selectedLocation();
    this.api.graphBuildingRisk({
      building: {
        addressText: this.addressCtrl.value || values.addressText,
        constructionYear: values.constructionYear,
        floorCount: values.floorCount,
        structuralSystem: values.structuralSystem,
        soilType: values.soilType,
        columnCracks: values.columnCracks,
        pastDamage: values.pastDamage,
        softStorey: values.softStorey,
        heavyTopFloor: values.heavyTopFloor,
        irregularShape: values.irregularShape,
        retrofitDone: values.retrofitDone,
      },
      location: location
        ? { latitude: location.lat, longitude: location.lng, label: location.label, source: location.source }
        : null,
    }).subscribe({
      next: (response) => {
        this.scoreLoading.set(false);
        const r = this.toRiskResult(response);
        this.result.set(r);
        this.animateScore(r.totalScore);
      },
      error: () => {
        this.scoreLoading.set(false);
        this.scoreError.set('AI risk skoru üretilemedi. Backend ve LangGraph servislerini kontrol et.');
      },
    });
  }

  searchAddress(): void {
    const query = this.addressCtrl.value.trim();
    if (query.length < 5) {
      this.geocodeError.set('Lütfen en az mahalle/sokak düzeyinde bir adres gir.');
      return;
    }

    this.geocodeLoading.set(true);
    this.geocodeError.set(null);
    this.locationError.set(null);

    this.geocodeApi.search(query).subscribe({
      next: (result) => {
        this.geocodeLoading.set(false);
        this.setLocation(result.latitude, result.longitude, 'address', result.displayName);
      },
      error: () => {
        this.geocodeLoading.set(false);
        this.geocodeError.set('Adres bulunamadı. Daha net bir adres, ilçe veya mahalle eklemeyi dene.');
      },
    });
  }

  useMyLocation(): void {
    this.locationError.set(null);
    this.geocodeError.set(null);
    if (!('geolocation' in navigator)) {
      this.locationError.set('Bu tarayıcıda konum servisi desteklenmiyor.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        this.setLocation(position.coords.latitude, position.coords.longitude, 'device');
      },
      () => {
        this.locationError.set('Cihaz konumu alınamadı. Adres aramayı deneyebilirsin.');
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  private animateScore(target: number): void {
    const duration = 1200;
    const start = performance.now();
    const tick = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      this.displayScore.set(Math.round(eased * target));
      if (progress < 1) {
        this.scoreAnimationFrame = requestAnimationFrame(tick);
      }
    };
    this.scoreAnimationFrame = requestAnimationFrame(tick);
  }

  private initMap(): void {
    if (!this.riskMapEl || this.map) return;

    this.map = L.map(this.riskMapEl.nativeElement, {
      center: [39.0, 35.0],
      zoom: 6,
      minZoom: 5,
      maxZoom: 12,
      maxBounds: [[35.0, 25.0], [43.4, 45.4]],
      maxBoundsViscosity: 1,
      attributionControl: false,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}{r}.png', {
      maxZoom: 18,
    }).addTo(this.map);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png', {
      maxZoom: 18,
      pane: 'overlayPane',
    }).addTo(this.map);

    this.selectionLayer.addTo(this.map);
    window.setTimeout(() => this.map?.invalidateSize(), 100);
  }

  private setLocation(lat: number, lng: number, source: 'address' | 'device', label?: string): void {
    this.selectedLocation.set({ lat, lng, source, label });
    this.locationError.set(null);
    this.drawSelection(lat, lng);
    this.map?.flyTo([lat, lng], 13, { duration: 0.6 });
    this.loadSoilAt(lat, lng);
  }

  private drawSelection(lat: number, lng: number): void {
    this.selectionLayer.clearLayers();
    L.circleMarker([lat, lng], {
      radius: 7,
      color: '#ffffff',
      weight: 2,
      fillColor: '#7dd3fc',
      fillOpacity: 1,
    }).addTo(this.selectionLayer);
    L.circle([lat, lng], {
      radius: 320,
      color: '#7dd3fc',
      weight: 1,
      opacity: 0.7,
      fillOpacity: 0.08,
    }).addTo(this.selectionLayer);
  }

  private loadSoilAt(lat: number, lng: number): void {
    const delta = 0.18;
    this.soilLoading.set(true);
    this.soilHint.set(null);
    this.soilError.set(null);

    this.soilApi.getSoilZones({ bbox: [lng - delta, lat - delta, lng + delta, lat + delta] }).subscribe({
      next: (geojson) => {
        const siteClass = this.findSiteClassAtPoint(lat, lng, geojson);
        if (siteClass) {
          this.form.patchValue({ soilType: siteClass });
          this.soilHint.set(`Bu konum için zemin sınıfı ${siteClass} otomatik seçildi.`);
        } else {
          this.soilHint.set('Bu konum için zemin sınıfı bulunamadı; manuel seçim yapabilirsin.');
        }
        this.soilLoading.set(false);
      },
      error: () => {
        this.soilLoading.set(false);
        this.soilError.set('Zemin katmanı alınamadı. Soil API çalışıyor mu?');
      },
    });
  }

  private findSiteClassAtPoint(lat: number, lng: number, geojson: SoilZoneGeoJson): string | null {
    for (const feature of geojson.features) {
      if (this.featureContainsPoint(feature, lat, lng)) {
        return this.normalizeSiteClass(feature.properties?.siteClass);
      }
    }
    return null;
  }

  private featureContainsPoint(feature: SoilZoneGeoJson['features'][number], lat: number, lng: number): boolean {
    const geometry = feature.geometry;
    if (geometry.type === 'Polygon') return this.polygonContainsPoint(geometry.coordinates as number[][][], lat, lng);
    if (geometry.type === 'MultiPolygon') return (geometry.coordinates as number[][][][]).some((p) => this.polygonContainsPoint(p, lat, lng));
    return false;
  }

  private polygonContainsPoint(rings: number[][][], lat: number, lng: number): boolean {
    if (rings.length === 0) return false;
    if (!this.ringContainsPoint(rings[0], lat, lng)) return false;
    for (let i = 1; i < rings.length; i++) if (this.ringContainsPoint(rings[i], lat, lng)) return false;
    return true;
  }

  private ringContainsPoint(ring: number[][], lat: number, lng: number): boolean {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i];
      const [xj, yj] = ring[j];
      if (((yi > lat) !== (yj > lat)) && lng < ((xj - xi) * (lat - yi)) / ((yj - yi) || Number.EPSILON) + xi) {
        inside = !inside;
      }
    }
    return inside;
  }

  private normalizeSiteClass(value: unknown): string | null {
    if (typeof value !== 'string') return null;
    const cleaned = value.trim().toUpperCase();
    return ['ZA', 'ZB', 'ZC', 'ZD', 'ZE', 'ZF'].includes(cleaned) ? cleaned : null;
  }

  private toRiskResult(response: GraphBuildingRiskResponse): RiskResult {
    const level = this.normalizeLevel(response.level);
    return {
      totalScore: response.totalScore,
      level,
      label: response.label,
      color: this.levelColor(level),
      confidence: response.confidence,
      summary: response.summary,
      primaryDrivers: response.primaryDrivers ?? [],
      buildingDrivers: response.buildingDrivers ?? [],
      locationDrivers: response.locationDrivers ?? [],
      recommendedActions: response.recommendedActions ?? [],
      cautions: response.cautions ?? [],
      componentScores: response.componentScores ?? {},
      context: response.context ?? {},
      sources: response.sources ?? [],
    };
  }

  private normalizeLevel(value: string): RiskResult['level'] {
    if (value === 'dusuk' || value === 'orta' || value === 'yuksek' || value === 'kritik') return value;
    return 'orta';
  }

  private levelColor(level: RiskResult['level']): string {
    switch (level) {
      case 'dusuk': return '#22c55e';
      case 'orta': return '#eab308';
      case 'yuksek': return '#f97316';
      case 'kritik': return '#ef4444';
    }
  }
}
