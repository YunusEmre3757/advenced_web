import { AfterViewInit, Component, ElementRef, OnDestroy, OnInit, ViewChild, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import * as L from 'leaflet';
import { Earthquake, EarthquakeApi, EarthquakeDetail } from '../../core/earthquake-api';
import { AiApi, GraphQuakeDetailResponse } from '../../core/ai-api';
import { ExposureApi, ExposureEstimate } from '../../core/exposure-api';
import { OmoriChart } from '../../shared/omori-chart/omori-chart';

@Component({
  selector: 'app-earthquake-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, OmoriChart],
  templateUrl: './earthquake-detail.html',
  styleUrl: './earthquake-detail.css'
})
export class EarthquakeDetailPage implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('detailMap', { static: false }) detailMapEl!: ElementRef<HTMLDivElement>;

  detail = signal<EarthquakeDetail | null>(null);
  loading = signal(true);
  error = signal<string | null>(null);
  populationImpact = signal<ExposureEstimate | null>(null);
  populationLoading = signal(false);
  populationError = signal<string | null>(null);
  aiSummary = signal<GraphQuakeDetailResponse | null>(null);
  aiLoading = signal(false);
  aiError = signal<string | null>(null);

  private routeSub?: Subscription;
  private map?: L.Map;
  private markerLayer = L.layerGroup();
  private shakeLayer = L.layerGroup();
  private readonly turkeyBounds: L.LatLngBoundsLiteral = [[35.0, 25.0], [43.4, 45.4]];
  private currentEventId: string | null = null;

  constructor(
    private readonly route: ActivatedRoute,
    private readonly earthquakeApi: EarthquakeApi,
    private readonly aiApi: AiApi,
    private readonly exposureApi: ExposureApi
  ) { }

  ngOnInit(): void {
    this.routeSub = this.route.paramMap.subscribe((params) => {
      const id = params.get('id');
      if (!id) {
        this.error.set('Deprem kaydi bulunamadi.');
        this.loading.set(false);
        return;
      }
      this.currentEventId = id;
      this.loadDetail(id);
    });
  }

  ngAfterViewInit(): void {
    this.initMap();
    const current = this.detail();
    if (current) this.renderMap(current);
  }

  ngOnDestroy(): void {
    this.routeSub?.unsubscribe();
    if (this.map) this.map.remove();
  }

  loadDetail(id: string): void {
    this.loading.set(true);
    this.error.set(null);
    this.populationImpact.set(null);
    this.populationError.set(null);
    this.aiSummary.set(null);
    this.aiError.set(null);
    this.earthquakeApi.getDetail(id).subscribe({
      next: (detail) => {
        this.detail.set(detail);
        this.loadExposure(detail.event);
        this.loading.set(false);
        window.setTimeout(() => {
          if (!this.map) this.initMap();
          this.renderMap(detail);
        }, 0);
      },
      error: () => {
        this.detail.set(null);
        this.loading.set(false);
        this.error.set('Deprem detayi su anda alinamiyor. Kaynak akisinda kayit zaman asimina ugramis olabilir.');
      }
    });
  }

  private loadExposure(event: Earthquake): void {
    this.populationLoading.set(true);
    this.populationError.set(null);
    this.exposureApi.estimate(event.lat, event.lng, event.mag, event.depth).subscribe({
      next: (estimate) => {
        this.populationImpact.set(estimate);
        this.populationLoading.set(false);
      },
      error: () => {
        this.populationImpact.set(null);
        this.populationLoading.set(false);
        this.populationError.set('WorldPop grid tabanli nufus verisi alinamadi.');
      }
    });
  }

  runAiSummary(): void {
    if (!this.currentEventId || this.aiLoading()) return;
    this.aiLoading.set(true);
    this.aiError.set(null);
    this.aiApi.graphQuakeDetail(this.currentEventId).subscribe({
      next: (result) => {
        this.aiSummary.set(result);
        this.aiLoading.set(false);
      },
      error: () => {
        this.aiLoading.set(false);
        this.aiError.set('LangGraph olay ozeti alinamadi. Graph servisi 8002 portunda calisiyor mu?');
      }
    });
  }

  quickRead(detail: EarthquakeDetail): string[] {
    const event = detail.event;
    const items: string[] = [];
    const mag = this.normalizedMag(event);
    if (mag >= 5) {
      items.push('M5+ olay: aile bildirimleri, guvendeyim akisi ve yerel duyurular aktif tutulmali.');
    } else if (mag >= 4) {
      items.push('Orta seviye olay: artci adaylari ve ayni bolgedeki yeni kayitlar yakindan izlenmeli.');
    } else {
      items.push('Dusuk seviye olay: rutin izleme yeterli, yakin bolge icin veri akisi acik tutulmali.');
    }

    if (event.depth <= 10) {
      items.push('Sig odakli deprem: yuzeyde hissedilme olasiligi daha yuksek.');
    } else if (event.depth >= 70) {
      items.push('Derin odakli deprem: genis alanda zayif hissedilebilir.');
    } else {
      items.push('Orta derinlik: yerel zemin kosullari hissedilme seviyesini belirgin etkileyebilir.');
    }

    if (detail.aftershocks.length > 0) {
      items.push(`${detail.aftershocks.length} artci aday kaydi bulundu.`);
    } else {
      items.push('Bu pencere icinde artci aday kaydi bulunmadi.');
    }
    return items;
  }

  normalizedMag(eq: Earthquake): number {
    return Math.round(eq.mag * 10) / 10;
  }

  relativeTime(date: Date): string {
    const diffMs = Date.now() - date.getTime();
    const min = Math.floor(diffMs / 60000);
    if (min < 1) return 'simdi';
    if (min < 60) return `${min} dk once`;
    const hour = Math.floor(min / 60);
    if (hour < 24) return `${hour} sa once`;
    const day = Math.floor(hour / 24);
    return `${day} gun once`;
  }

  magClass(value: number): 'high' | 'mid' | 'low' {
    if (value >= 5) return 'high';
    if (value >= 3) return 'mid';
    return 'low';
  }

  private initMap(): void {
    if (!this.detailMapEl) return;
    if (this.map) return;
    this.map = L.map(this.detailMapEl.nativeElement, {
      center: [39.0, 35.0],
      zoom: 6,
      minZoom: 5,
      maxZoom: 11,
      maxBounds: this.turkeyBounds,
      maxBoundsViscosity: 1,
      attributionControl: false,
      scrollWheelZoom: true
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}{r}.png', {
      maxZoom: 18
    }).addTo(this.map);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png', {
      maxZoom: 18,
      pane: 'overlayPane'
    }).addTo(this.map);

    this.shakeLayer.addTo(this.map);
    this.markerLayer.addTo(this.map);
    window.setTimeout(() => this.map?.invalidateSize(), 80);
  }

  private renderMap(detail: EarthquakeDetail): void {
    if (!this.map) return;
    this.map.invalidateSize();
    this.markerLayer.clearLayers();
    this.shakeLayer.clearLayers();

    const event = detail.event;
    const mag = this.normalizedMag(event);
    const center: L.LatLngExpression = [event.lat, event.lng];
    const colors = this.magColors(mag);
    const baseRadius = this.shakeRadiusKm(mag) * 1000;

    [
      { scale: 1, opacity: 0.16 },
      { scale: 0.62, opacity: 0.22 },
      { scale: 0.32, opacity: 0.30 }
    ].forEach((ring) => {
      L.circle(center, {
        radius: baseRadius * ring.scale,
        color: colors.stroke,
        fillColor: colors.fill,
        fillOpacity: ring.opacity,
        weight: 1
      }).addTo(this.shakeLayer);
    });

    L.circleMarker(center, {
      radius: mag >= 5 ? 13 : mag >= 4 ? 11 : 9,
      color: 'rgba(255,255,255,0.9)',
      fillColor: colors.stroke,
      fillOpacity: 0.95,
      weight: 2
    }).bindPopup(`<strong>${event.location}</strong><br>M${mag.toFixed(1)} | ${event.depth.toFixed(0)} km`)
      .addTo(this.markerLayer);

    detail.aftershocks.forEach((aftershock) => {
      const afterMag = this.normalizedMag(aftershock);
      const afterColors = this.magColors(afterMag);
      L.circleMarker([aftershock.lat, aftershock.lng], {
        radius: Math.max(4, afterMag + 2),
        color: 'rgba(6, 11, 20, 0.9)',
        fillColor: afterColors.stroke,
        fillOpacity: 0.78,
        weight: 1
      }).bindPopup(`<strong>${aftershock.location}</strong><br>M${afterMag.toFixed(1)} | ${aftershock.depth.toFixed(0)} km`)
        .addTo(this.markerLayer);
    });

    const points: L.LatLngExpression[] = [
      center,
      ...detail.aftershocks.map((item) => [item.lat, item.lng] as L.LatLngExpression)
    ];
    const bounds = L.latLngBounds(points);
    this.map.fitBounds(bounds.pad(0.28), { maxZoom: detail.aftershocks.length > 0 ? 9 : 8 });
    this.map.panInsideBounds(this.turkeyBounds);
  }

  private shakeRadiusKm(magnitude: number): number {
    if (magnitude >= 6) return 150;
    if (magnitude >= 5) return 90;
    if (magnitude >= 4) return 55;
    if (magnitude >= 3) return 30;
    return 16;
  }

  private magColors(magnitude: number): { stroke: string; fill: string } {
    if (magnitude >= 5) return { stroke: '#ef4444', fill: '#ef4444' };
    if (magnitude >= 4) return { stroke: '#f97316', fill: '#f97316' };
    if (magnitude >= 3) return { stroke: '#eab308', fill: '#eab308' };
    return { stroke: '#22c55e', fill: '#22c55e' };
  }
}
