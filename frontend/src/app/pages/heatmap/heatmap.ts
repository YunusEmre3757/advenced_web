import { AfterViewInit, Component, ElementRef, OnDestroy, ViewChild, inject, signal } from '@angular/core';
import * as maplibregl from 'maplibre-gl';
import { EarthquakeApi } from '../../core/earthquake-api';

@Component({
  selector: 'app-heatmap',
  standalone: true,
  imports: [],
  templateUrl: './heatmap.html',
  styleUrl: './heatmap.css',
})
export class HeatmapPage implements AfterViewInit, OnDestroy {
  @ViewChild('heatMap', { static: true }) mapEl!: ElementRef<HTMLDivElement>;
  private readonly api = inject(EarthquakeApi);

  readonly hours = signal(168);
  readonly minMag = signal(2.0);
  readonly count = signal(0);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  private map?: maplibregl.Map;

  ngAfterViewInit(): void {
    this.initMap();
  }

  ngOnDestroy(): void {
    this.map?.remove();
  }

  private initMap(): void {
    this.map = new maplibregl.Map({
      container: this.mapEl.nativeElement,
      style: {
        version: 8,
        sources: {
          raster: {
            type: 'raster',
            tiles: ['https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'.replace('{s}', 'a')],
            tileSize: 256,
          },
        },
        layers: [{ id: 'raster', type: 'raster', source: 'raster' }],
      },
      center: [35.0, 39.0],
      zoom: 5.2,
    });
    this.map.on('load', () => this.load());
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getRecent(this.hours(), this.minMag(), 500).subscribe({
      next: rows => {
        this.count.set(rows.length);
        const features = rows.map(r => ({
          type: 'Feature' as const,
          geometry: { type: 'Point' as const, coordinates: [r.lng, r.lat] },
          properties: { mag: r.mag },
        }));
        const geojson = { type: 'FeatureCollection' as const, features };
        const existing = this.map?.getSource('eq-heat') as maplibregl.GeoJSONSource | undefined;
        if (existing) {
          existing.setData(geojson);
        } else {
          this.map!.addSource('eq-heat', { type: 'geojson', data: geojson });
          this.map!.addLayer({
            id: 'eq-heat-layer',
            type: 'heatmap',
            source: 'eq-heat',
            paint: {
              'heatmap-weight': ['interpolate', ['linear'], ['get', 'mag'], 0, 0.1, 5, 1, 7, 2],
              'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 4, 1, 10, 3],
              'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 4, 12, 10, 36],
              'heatmap-opacity': 0.85,
              'heatmap-color': [
                'interpolate', ['linear'], ['heatmap-density'],
                0, 'rgba(0,0,0,0)',
                0.15, '#22c55e',
                0.35, '#eab308',
                0.6, '#f97316',
                0.85, '#ef4444',
                1, '#fecaca',
              ],
            },
          });
          this.map!.addLayer({
            id: 'eq-points',
            type: 'circle',
            source: 'eq-heat',
            minzoom: 7,
            paint: {
              'circle-radius': ['interpolate', ['linear'], ['get', 'mag'], 0, 2, 7, 10],
              'circle-color': '#fff',
              'circle-opacity': 0.85,
              'circle-stroke-width': 0.5,
              'circle-stroke-color': '#1e293b',
            },
          });
        }
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Veri alinamadi.');
      },
    });
  }

  setHours(h: number): void {
    this.hours.set(h);
    this.load();
  }

  setMinMag(m: number): void {
    this.minMag.set(m);
    this.load();
  }
}
