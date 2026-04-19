import { AfterViewInit, Component, ElementRef, OnDestroy, ViewChild, inject, signal } from '@angular/core';
import { forkJoin } from 'rxjs';
import * as L from 'leaflet';
import { HistoricalApi, HistoricalEvent, SeismicGap } from '../../core/historical-api';

@Component({
  selector: 'app-historical-map',
  standalone: true,
  imports: [],
  templateUrl: './historical-map.html',
  styleUrl: './historical-map.css',
})
export class HistoricalMap implements AfterViewInit, OnDestroy {
  @ViewChild('histMap', { static: true }) mapEl!: ElementRef<HTMLDivElement>;

  private readonly api = inject(HistoricalApi);

  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly eventCount = signal(0);
  readonly gapCount = signal(0);
  readonly showGaps = signal(true);
  readonly showEvents = signal(true);

  private map?: L.Map;
  private eventLayer = L.layerGroup();
  private gapLayer = L.layerGroup();
  private events: HistoricalEvent[] = [];
  private gaps: SeismicGap[] = [];

  ngAfterViewInit(): void {
    this.initMap();
    this.load();
  }

  ngOnDestroy(): void {
    if (this.map) this.map.remove();
  }

  private initMap(): void {
    this.map = L.map(this.mapEl.nativeElement, {
      center: [39.0, 35.0],
      zoom: 6,
      minZoom: 4,
      maxZoom: 11,
      scrollWheelZoom: true,
    });
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 18,
      attribution: '&copy; CartoDB',
    }).addTo(this.map);
    this.gapLayer.addTo(this.map);
    this.eventLayer.addTo(this.map);
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    forkJoin({
      events: this.api.events(50, 5.0),
      gaps: this.api.gaps(50, 5.5, 30, 18),
    }).subscribe({
      next: ({ events, gaps }) => {
        this.events = events;
        this.gaps = gaps;
        this.eventCount.set(events.length);
        this.gapCount.set(gaps.length);
        this.renderEvents();
        this.renderGaps();
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Tarihsel veri alinamadi. USGS servisi gecici erisilemez olabilir.');
      },
    });
  }

  private renderEvents(): void {
    this.eventLayer.clearLayers();
    if (!this.showEvents()) return;
    for (const e of this.events) {
      const color = this.colorFor(e.magnitude);
      L.circleMarker([e.latitude, e.longitude], {
        radius: Math.max(3, (e.magnitude - 4.5) * 3),
        color,
        fillColor: color,
        fillOpacity: 0.55,
        weight: 0.5,
      }).bindPopup(
        `<strong>${e.place || 'Konum yok'}</strong><br>` +
        `M${e.magnitude.toFixed(1)} &middot; ${new Date(e.time).toLocaleDateString('tr-TR')}<br>` +
        `Derinlik: ${e.depthKm.toFixed(0)} km`
      ).addTo(this.eventLayer);
    }
  }

  private renderGaps(): void {
    this.gapLayer.clearLayers();
    if (!this.showGaps()) return;
    for (const g of this.gaps) {
      const bounds: L.LatLngBoundsLiteral = [
        [g.centerLat - g.latSpan / 2, g.centerLon - g.lonSpan / 2],
        [g.centerLat + g.latSpan / 2, g.centerLon + g.lonSpan / 2],
      ];
      L.rectangle(bounds, {
        color: '#f97316',
        weight: 1,
        fillColor: '#f97316',
        fillOpacity: 0.22,
      }).bindPopup(
        `<strong>Sismik bosluk</strong><br>` +
        `${g.silentYears} yildir M${g.magnitudeThreshold.toFixed(1)}+ kaydi yok.<br>` +
        `<em>Gecmiste bu bolgede buyuk olay var, son donemde sessiz.</em>`
      ).addTo(this.gapLayer);
    }
  }

  toggleEvents(): void {
    this.showEvents.update(v => !v);
    this.renderEvents();
  }

  toggleGaps(): void {
    this.showGaps.update(v => !v);
    this.renderGaps();
  }

  private colorFor(mag: number): string {
    if (mag >= 7) return '#ef4444';
    if (mag >= 6) return '#f97316';
    if (mag >= 5.5) return '#eab308';
    return '#22c55e';
  }
}
