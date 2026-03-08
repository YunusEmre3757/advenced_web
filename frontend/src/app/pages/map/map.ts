import {
  AfterViewInit,
  Component,
  ElementRef,
  OnDestroy,
  OnInit,
  ViewChild,
  computed,
  signal
} from '@angular/core';
import { CommonModule } from '@angular/common';
import * as maplibregl from 'maplibre-gl';
import { Earthquake, EarthquakeApi } from '../../core/earthquake-api';
import { FaultLineApi, FaultLineGeoJson } from '../../core/fault-line-api';
import { SoilZoneApi, SoilZoneGeoJson } from '../../core/soil-zone-api';
import { AiApi } from '../../core/ai-api';

type AiRole = 'user' | 'assistant';
interface AiMessage {
  role: AiRole;
  text: string;
  meta?: string | null;
}

@Component({
  selector: 'app-map',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './map.html',
  styleUrl: './map.css'
})
export class Map implements OnInit, OnDestroy, AfterViewInit {
  @ViewChild('mainMap', { static: false }) mapEl!: ElementRef;

  private map!: maplibregl.Map;
  private mapLoaded = false;
  private refreshTimer: ReturnType<typeof setInterval> | null = null;
  private searchTimer: ReturnType<typeof setTimeout> | null = null;
  private faultFetchTimer: ReturnType<typeof setTimeout> | null = null;
  private soilFetchTimer: ReturnType<typeof setTimeout> | null = null;
  private viewportInitialized = false;
  private faultRequestToken = 0;
  private soilRequestToken = 0;
  private lastFaultQueryKey: string | null = null;
  private lastSoilQueryKey: string | null = null;
  private eqPopup: maplibregl.Popup | null = null;
  private faultPopup: maplibregl.Popup | null = null;

  private readonly earthquakeSourceId = 'earthquakes';
  private readonly earthquakeCircleLayerId = 'eq-circles';
  private readonly earthquakeLabelLayerId = 'eq-labels';
  private readonly faultSourceId = 'fault-lines-src';
  private readonly faultLayerId = 'fault-lines';
  private readonly soilSourceId = 'soil-zones-src';
  private readonly soilFillLayerId = 'soil-zones-fill';
  private readonly soilLineLayerId = 'soil-zones-line';

  earthquakes = signal<Earthquake[]>([]);
  lastEq = signal<Earthquake | null>(null);
  loading = signal<boolean>(false);
  requestError = signal<string | null>(null);
  faultError = signal<string | null>(null);
  soilError = signal<string | null>(null);

  searchTerm = signal<string>('');
  minMag = signal<number>(1.0);
  depthFilter = signal<'all' | 'shallow' | 'medium' | 'deep'>('all');
  timeWindowHours = signal<number>(24);

  showFaults = signal<boolean>(true);
  showGround = signal<boolean>(false);
  showRecent = signal<boolean>(true);
  filtersOpen = signal<boolean>(true);
  rightDrawerOpen = signal<boolean>(false);
  rightDrawerTab = signal<'layers' | 'legend'>('layers');
  aiDockOpen = signal<boolean>(false);

  faultGeoJson = signal<FaultLineGeoJson | null>(null);
  soilGeoJson = signal<SoilZoneGeoJson | null>(null);
  filteredCount = signal<number>(0);
  selectedEventId = signal<string | null>(null);
  aiMessages = signal<AiMessage[]>([
    {
      role: 'assistant',
      text: 'AI hazir. Fay/deprem sorunu yaz, secili harita penceresine gore yanitlayayim.'
    }
  ]);
  aiInput = signal<string>('');
  aiLoading = signal<boolean>(false);
  aiError = signal<string | null>(null);
  selectedEq = computed(() => {
    const id = this.selectedEventId();
    if (!id) return null;
    return this.earthquakes().find((e) => e.id === id) ?? null;
  });

  readonly windowStartLabel = computed(() => {
    const end = new Date();
    const start = new Date(end.getTime() - this.timeWindowHours() * 60 * 60 * 1000);
    return this.formatDate(start);
  });

  readonly windowEndLabel = computed(() => this.formatDate(new Date()));

  constructor(
    private readonly earthquakeApi: EarthquakeApi,
    private readonly faultLineApi: FaultLineApi,
    private readonly soilZoneApi: SoilZoneApi,
    private readonly aiApi: AiApi
  ) {}

  ngOnInit(): void {
    this.fetchData();
    this.refreshTimer = setInterval(() => this.fetchData(false), 45_000);
  }

  ngAfterViewInit(): void {
    this.initMap();
  }

  ngOnDestroy(): void {
    if (this.refreshTimer) clearInterval(this.refreshTimer);
    if (this.searchTimer) clearTimeout(this.searchTimer);
    if (this.faultFetchTimer) clearTimeout(this.faultFetchTimer);
    if (this.soilFetchTimer) clearTimeout(this.soilFetchTimer);
    if (this.eqPopup) this.eqPopup.remove();
    if (this.faultPopup) this.faultPopup.remove();
    if (this.map) this.map.remove();
  }

  private initMap(): void {
    this.map = new maplibregl.Map({
      container: this.mapEl.nativeElement,
      style: {
        version: 8,
        sources: {
          basemap: {
            type: 'raster',
            tiles: [
              'https://a.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}.png',
              'https://b.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}.png',
              'https://c.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}.png'
            ],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap &copy; CARTO'
          },
          labels: {
            type: 'raster',
            tiles: [
              'https://a.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png',
              'https://b.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png',
              'https://c.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png'
            ],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap &copy; CARTO'
          }
        },
        layers: [
          {
            id: 'base-light',
            type: 'raster',
            source: 'basemap'
          },
          {
            id: 'base-labels',
            type: 'raster',
            source: 'labels'
          }
        ]
      },
      center: [35.0, 39.0],
      zoom: 6,
      minZoom: 5,
      maxZoom: 12,
      maxBounds: [[25.0, 35.0], [45.0, 43.0]],
      attributionControl: false
    });

    this.map.on('load', () => {
      this.mapLoaded = true;
      this.installSourcesAndLayers();
      this.redrawAll();
    });

    this.map.on('zoomend', () => {
      this.drawMarkers();
      this.scheduleFaultFetch();
      this.scheduleSoilFetch();
    });

    this.map.on('moveend', () => {
      this.scheduleFaultFetch();
      this.scheduleSoilFetch();
    });

    this.map.on('click', this.earthquakeCircleLayerId, (event: maplibregl.MapLayerMouseEvent) => {
      this.openEqPopup(event);
    });

    this.map.on('mouseenter', this.earthquakeCircleLayerId, () => {
      this.map.getCanvas().style.cursor = 'pointer';
    });

    this.map.on('mouseleave', this.earthquakeCircleLayerId, () => {
      this.map.getCanvas().style.cursor = '';
    });

    this.map.on('click', this.faultLayerId, (event: maplibregl.MapLayerMouseEvent) => {
      this.openFaultPopup(event);
    });

    this.map.on('mouseenter', this.faultLayerId, () => {
      this.map.getCanvas().style.cursor = 'pointer';
    });

    this.map.on('mouseleave', this.faultLayerId, () => {
      this.map.getCanvas().style.cursor = '';
    });
  }

  private installSourcesAndLayers(): void {
    if (!this.mapLoaded) return;

    if (!this.map.getSource(this.earthquakeSourceId)) {
      this.map.addSource(this.earthquakeSourceId, {
        type: 'geojson',
        data: this.emptyFeatureCollection()
      });
    }

    if (!this.map.getSource(this.soilSourceId)) {
      this.map.addSource(this.soilSourceId, {
        type: 'geojson',
        data: this.emptyFeatureCollection()
      });
    }

    if (!this.map.getLayer(this.soilFillLayerId)) {
      this.map.addLayer({
        id: this.soilFillLayerId,
        type: 'fill',
        source: this.soilSourceId,
        paint: {
          'fill-color': [
            'match',
            ['coalesce', ['get', 'siteClass'], 'UNKNOWN'],
            'ZA', 'rgba(34,197,94,0.38)',
            'ZB', 'rgba(132,204,22,0.40)',
            'ZC', 'rgba(250,204,21,0.42)',
            'ZD', 'rgba(249,115,22,0.44)',
            'ZE', 'rgba(239,68,68,0.46)',
            'ZF', 'rgba(153,27,27,0.50)',
            'rgba(148,163,184,0.32)'
          ],
          'fill-opacity': [
            'interpolate', ['linear'], ['zoom'],
            5, 0.10,
            8, 0.18,
            12, 0.26
          ]
        },
        layout: { visibility: 'none' }
      });
    }

    if (!this.map.getLayer(this.soilLineLayerId)) {
      this.map.addLayer({
        id: this.soilLineLayerId,
        type: 'line',
        source: this.soilSourceId,
        paint: {
          'line-color': [
            'match',
            ['coalesce', ['get', 'siteClass'], 'UNKNOWN'],
            'ZA', '#16a34a',
            'ZB', '#65a30d',
            'ZC', '#ca8a04',
            'ZD', '#ea580c',
            'ZE', '#dc2626',
            'ZF', '#7f1d1d',
            '#64748b'
          ],
          'line-width': [
            'interpolate', ['linear'], ['zoom'],
            5, 0.2,
            8, 0.5,
            12, 0.9
          ],
          'line-opacity': 0.28
        },
        layout: { visibility: 'none' }
      });
    }

    if (!this.map.getLayer(this.earthquakeCircleLayerId)) {
      this.map.addLayer({
        id: this.earthquakeCircleLayerId,
        type: 'circle',
        source: this.earthquakeSourceId,
        paint: {
          'circle-color': ['coalesce', ['get', 'color'], '#22c55e'],
          'circle-radius': ['coalesce', ['get', 'radius'], 4],
          'circle-opacity': ['coalesce', ['get', 'opacity'], 0.85],
          'circle-stroke-color': 'rgba(0, 0, 0, 0.35)',
          'circle-stroke-width': 1
        }
      });
    }

    if (!this.map.getLayer(this.earthquakeLabelLayerId)) {
      this.map.addLayer({
        id: this.earthquakeLabelLayerId,
        type: 'symbol',
        source: this.earthquakeSourceId,
        minzoom: 7,
        filter: ['>=', ['get', 'mag'], 3],
        layout: {
          'text-field': ['get', 'magLabel'],
          'text-size': 12,
          'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
          'text-offset': [0, -1.2],
          'text-anchor': 'top',
          'text-allow-overlap': false
        },
        paint: {
          'text-color': '#111827',
          'text-halo-color': 'rgba(255,255,255,0.92)',
          'text-halo-width': 1.1
        }
      });
    }

    if (!this.map.getSource(this.faultSourceId)) {
      this.map.addSource(this.faultSourceId, {
        type: 'geojson',
        data: this.emptyFeatureCollection()
      });
    }

    if (!this.map.getLayer(this.faultLayerId)) {
      this.map.addLayer({
        id: this.faultLayerId,
        type: 'line',
        source: this.faultSourceId,
        layout: {
          'line-cap': 'round',
          'line-join': 'round'
        },
        paint: {
          'line-color': '#ef4444',
          'line-width': [
            'interpolate', ['linear'], ['zoom'],
            5, 0.7,
            8, 1.1,
            12, 1.5
          ],
          'line-opacity': 0.5
        }
      });
    }
  }

  private redrawAll(): void {
    this.drawMarkers();
    this.scheduleFaultFetch();
    this.scheduleSoilFetch();
  }

  private applyFilters(): Earthquake[] {
    if (!this.showRecent()) return [];

    const cutoff = Date.now() - this.timeWindowHours() * 60 * 60 * 1000;
    const queryRaw = this.searchTerm();
    const query = this.normalizeText(queryRaw);
    const queryIsCoordinates = this.tryParseCoordinates(queryRaw) !== null;

    const filtered = this.earthquakes().filter((eq) => {
      if (eq.date.getTime() < cutoff) return false;
      if (eq.mag < this.minMag()) return false;

      if (this.depthFilter() === 'shallow' && eq.depth > 70) return false;
      if (this.depthFilter() === 'medium' && (eq.depth <= 70 || eq.depth > 300)) return false;
      if (this.depthFilter() === 'deep' && eq.depth <= 300) return false;

      if (!query || queryIsCoordinates) return true;
      return this.normalizeText(eq.location).includes(query);
    });

    filtered.sort((a, b) => b.date.getTime() - a.date.getTime());

    const zoom = this.mapLoaded ? this.map.getZoom() : 6;
    let cap = zoom >= 9 ? 420 : zoom >= 7 ? 280 : 160;
    if (this.showFaults()) {
      cap = Math.floor(cap * 0.7);
    }
    return filtered.slice(0, cap);
  }

  private drawMarkers(): void {
    if (!this.mapLoaded) return;

    const data = this.applyFilters();
    this.filteredCount.set(data.length);

    const src = this.map.getSource(this.earthquakeSourceId) as maplibregl.GeoJSONSource | undefined;
    if (!src) return;

    const features: GeoJSON.Feature<GeoJSON.Point, Record<string, string | number>>[] = data.map((eq) => {
      const mag = this.normalizedMag(eq.mag);
      const radius = mag >= 6 ? 12 : mag >= 5 ? 10 : mag >= 4 ? 8 : mag >= 3 ? 6 : 4;

      const magnitudeColor = mag >= 5 ? '#ef4444' : mag >= 3 ? '#f97316' : '#22c55e';
      const color = magnitudeColor;

      return {
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [eq.lng, eq.lat]
        },
        properties: {
          id: eq.id,
          location: eq.location,
          dateText: this.formatDate(eq.date),
          mag,
          magLabel: mag.toFixed(1),
          depth: Number(eq.depth.toFixed(0)),
          color,
          radius,
          opacity: Math.min(0.92, mag / 10 + 0.35)
        }
      };
    });

    src.setData({
      type: 'FeatureCollection',
      features
    });

    const labelsEnabled = this.map.getZoom() >= 7 && data.length <= 220;
    this.map.setLayoutProperty(
      this.earthquakeLabelLayerId,
      'visibility',
      labelsEnabled ? 'visible' : 'none'
    );

    this.drawGroundZones();

    if (!this.viewportInitialized && data.length > 0) {
      const bounds = new maplibregl.LngLatBounds();
      data.forEach((eq) => bounds.extend([eq.lng, eq.lat]));
      if (!bounds.isEmpty()) {
        this.map.fitBounds(bounds, { padding: 50, duration: 0 });
        this.viewportInitialized = true;
      }
    }
  }

  private drawFaults(): void {
    if (!this.mapLoaded) return;

    const source = this.map.getSource(this.faultSourceId) as maplibregl.GeoJSONSource | undefined;
    if (!source) return;

    const hasData = this.showFaults() && this.faultGeoJson() !== null;
    const data = hasData ? this.faultGeoJson()! : this.emptyFeatureCollection();
    source.setData(data as GeoJSON.FeatureCollection);

    this.map.setLayoutProperty(
      this.faultLayerId,
      'visibility',
      this.showFaults() ? 'visible' : 'none'
    );
  }

  private drawGroundZones(): void {
    if (!this.mapLoaded) return;
    const source = this.map.getSource(this.soilSourceId) as maplibregl.GeoJSONSource | undefined;
    if (!source) return;

    const hasData = this.showGround() && this.soilGeoJson() !== null;
    source.setData((hasData ? this.soilGeoJson()! : this.emptyFeatureCollection()) as GeoJSON.FeatureCollection);

    if (this.map.getLayer(this.soilFillLayerId)) {
      this.map.setLayoutProperty(
        this.soilFillLayerId,
        'visibility',
        this.showGround() ? 'visible' : 'none'
      );
    }

    if (this.map.getLayer(this.soilLineLayerId)) {
      this.map.setLayoutProperty(
        this.soilLineLayerId,
        'visibility',
        this.showGround() ? 'visible' : 'none'
      );
    }
  }

  private scheduleSoilFetch(): void {
    if (!this.mapLoaded || !this.showGround()) return;
    if (this.soilFetchTimer) clearTimeout(this.soilFetchTimer);
    this.soilFetchTimer = setTimeout(() => this.fetchSoilZonesForViewport(), 260);
  }

  private fetchSoilZonesForViewport(): void {
    if (!this.mapLoaded || !this.showGround()) return;

    const bounds = this.map.getBounds();
    const bbox: [number, number, number, number] = [
      bounds.getWest(),
      bounds.getSouth(),
      bounds.getEast(),
      bounds.getNorth()
    ];

    const queryKey = bbox.map((n) => n.toFixed(3)).join(',');
    if (queryKey === this.lastSoilQueryKey) return;
    this.lastSoilQueryKey = queryKey;

    const token = ++this.soilRequestToken;
    this.soilError.set(null);

    this.soilZoneApi.getSoilZones({ bbox }).subscribe({
      next: (geo) => {
        if (token !== this.soilRequestToken) return;
        this.soilGeoJson.set(geo);
        this.soilError.set(
          geo.features.length === 0
            ? 'Gercek zemin zonu verisi bulunamadi. ZA-ZF / Vs30 GeoJSON yukleyin.'
            : null
        );
        this.drawGroundZones();
      },
      error: () => {
        if (token !== this.soilRequestToken) return;
        this.soilGeoJson.set(null);
        this.soilError.set('Zemin katmani yuklenemedi. Soil GeoJSON importunu kontrol edin.');
        this.drawGroundZones();
      }
    });
  }

  private fetchData(showLoader = true): void {
    if (showLoader) this.loading.set(true);
    this.requestError.set(null);

    const hours = this.timeWindowHours();
    this.earthquakeApi.getRecent(hours, 0, 500).subscribe({
      next: (arr) => {
        const sorted = [...arr].sort((a, b) => b.date.getTime() - a.date.getTime());
        this.earthquakes.set(sorted);
        this.lastEq.set(sorted.length > 0 ? sorted[0] : null);
        this.loading.set(false);
        this.drawMarkers();
      },
      error: () => {
        this.earthquakes.set([]);
        this.lastEq.set(null);
        this.filteredCount.set(0);
        this.requestError.set('Canli deprem verisi alinamiyor. Backend/Kandilli baglantisini kontrol edin.');
        this.loading.set(false);
        this.drawMarkers();
      }
    });
  }

  private scheduleFaultFetch(): void {
    if (!this.mapLoaded || !this.showFaults()) return;
    if (this.faultFetchTimer) clearTimeout(this.faultFetchTimer);
    this.faultFetchTimer = setTimeout(() => this.fetchFaultLinesForViewport(), 240);
  }

  private fetchFaultLinesForViewport(): void {
    if (!this.mapLoaded || !this.showFaults()) return;

    const bounds = this.map.getBounds();
    const bbox: [number, number, number, number] = [
      bounds.getWest(),
      bounds.getSouth(),
      bounds.getEast(),
      bounds.getNorth()
    ];

    const simplify = this.faultSimplifyTolerance(this.map.getZoom());
    const queryKey = `${bbox.map((n) => n.toFixed(3)).join(',')}|${simplify.toFixed(4)}`;
    if (queryKey === this.lastFaultQueryKey) return;
    this.lastFaultQueryKey = queryKey;

    const token = ++this.faultRequestToken;

    this.faultError.set(null);
    this.faultLineApi.getFaultLines({ bbox, simplify }).subscribe({
      next: (geo) => {
        if (token !== this.faultRequestToken) return;
        this.faultGeoJson.set(geo);
        this.drawFaults();
      },
      error: () => {
        if (token !== this.faultRequestToken) return;
        this.faultGeoJson.set(null);
        this.faultError.set('Fay hatti katmani yuklenemedi. MTA GeoJSON importunu kontrol edin.');
        this.drawFaults();
      }
    });
  }

  private faultSimplifyTolerance(zoom: number): number {
    if (zoom <= 6) return 0.03;
    if (zoom <= 8) return 0.015;
    if (zoom <= 10) return 0.008;
    return 0.004;
  }

  private openEqPopup(event: maplibregl.MapLayerMouseEvent): void {
    const feature = event.features?.[0];
    if (!feature || feature.geometry.type !== 'Point') return;

    const coords = feature.geometry.coordinates as [number, number];
    const props = (feature.properties ?? {}) as Record<string, string | number>;

    const location = String(props['location'] ?? '-');
    const eventId = String(props['id'] ?? '');
    const mag = Number(props['mag'] ?? 0).toFixed(1);
    const depth = Number(props['depth'] ?? 0).toFixed(0);
    const dateText = String(props['dateText'] ?? '-');

    if (this.eqPopup) this.eqPopup.remove();

    this.eqPopup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: true,
      offset: 12,
      className: 'eq-popup'
    })
      .setLngLat(coords)
      .setHTML(
        `<div class="eqp-title">${location}</div>` +
        `<div class="eqp-meta">M${mag} | ${depth} km | ${dateText}</div>` +
        `<button class="eqp-ai-btn" type="button">AI ile analiz et</button>`
      )
      .addTo(this.map);

    if (eventId) {
      this.selectedEventId.set(eventId);
    }

    const popupEl = this.eqPopup.getElement();
    const aiBtn = popupEl?.querySelector('.eqp-ai-btn') as HTMLButtonElement | null;
    if (aiBtn) {
      aiBtn.onclick = () => this.openAiFromSelectedEvent(location);
    }
  }

  private openAiFromSelectedEvent(locationLabel: string): void {
    const selected = this.selectedEq();
    const fallbackLabel = selected?.location ?? locationLabel;
    this.aiDockOpen.set(true);
    this.sendAiMessage(
      `Secili depremi analiz et: ${fallbackLabel}. ` +
      `Bu depremin hangi fayla iliskili olabilecegini, mesafeyi, belirsizlik nedenlerini ` +
      `ve bu fayin temel ozelliklerini (kayma tipi/hiz/son hareket) veriyle ozetle.`
    );
  }

  private openFaultPopup(event: maplibregl.MapLayerMouseEvent): void {
    const feature = event.features?.[0];
    if (!feature) return;

    const coord = this.firstFaultCoordinate(feature.geometry);
    if (!coord) return;

    const props = (feature.properties ?? {}) as Record<string, unknown>;
    const title = this.faultSummaryFromProperties(props);
    const extra = this.stripHtml(String(
      props['description'] ?? props['ACIKLAMA'] ?? props['aciklama'] ?? ''
    ));

    if (this.faultPopup) this.faultPopup.remove();

    this.faultPopup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: true,
      offset: 10
    })
      .setLngLat(coord)
      .setHTML(
        `<div style="font-size:13px;font-weight:700;color:#1a1a2e">${title}</div>` +
        `<div style="font-size:12px;color:#555;max-width:260px">${extra || 'Fay segment bilgisi'}</div>`
      )
      .addTo(this.map);
  }

  private firstFaultCoordinate(geometry: GeoJSON.Geometry): [number, number] | null {
    if (geometry.type === 'LineString') {
      const coords = geometry.coordinates as number[][];
      if (!coords.length || coords[0].length < 2) return null;
      return [coords[0][0], coords[0][1]];
    }
    if (geometry.type === 'MultiLineString') {
      const lines = geometry.coordinates as number[][][];
      if (!lines.length || !lines[0].length || lines[0][0].length < 2) return null;
      return [lines[0][0][0], lines[0][0][1]];
    }
    return null;
  }

  private faultSummaryFromProperties(props: Record<string, unknown>): string {
    const pick = (key: string) => {
      const raw = props[key];
      if (typeof raw === 'string') return this.stripHtml(raw);
      return '';
    };

    const direct = pick('name') || pick('faultName') || pick('ACIKLAMA') || pick('aciklama');
    if (direct) return direct;

    const desc = props['description'];
    if (typeof desc === 'string') {
      const cleaned = this.stripHtml(desc);
      if (cleaned) return cleaned;
    }

    if (desc && typeof desc === 'object') {
      const value = (desc as Record<string, unknown>)['value'];
      if (typeof value === 'string') {
        const cleaned = this.stripHtml(value);
        if (cleaned) return cleaned;
      }
    }

    return 'Fay segmenti';
  }

  private stripHtml(input: string): string {
    return input
      .replace(/<[^>]*>/g, ' ')
      .replace(/&nbsp;/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  onSearchInput(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.searchTerm.set(value);

    const coords = this.tryParseCoordinates(value);
    if (coords && this.mapLoaded) {
      this.map.easeTo({ center: [coords.lng, coords.lat], zoom: 8, duration: 350 });
    }

    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.drawMarkers(), 180);
  }

  onMagChange(event: Event): void {
    const value = Number((event.target as HTMLInputElement).value);
    this.minMag.set(Number.isFinite(value) ? value : 1);
    this.drawMarkers();
  }

  setTimeWindow(hours: number): void {
    if (hours === this.timeWindowHours()) return;
    this.timeWindowHours.set(hours);
    this.fetchData();
  }

  setDepth(type: 'all' | 'shallow' | 'medium' | 'deep'): void {
    this.depthFilter.set(type);
    this.drawMarkers();
  }

  toggleFaults(): void {
    this.showFaults.set(!this.showFaults());
    if (this.showFaults()) {
      this.lastFaultQueryKey = null;
      this.scheduleFaultFetch();
    } else {
      this.faultRequestToken++;
      this.drawFaults();
    }
  }

  toggleGround(): void {
    this.showGround.set(!this.showGround());
    if (this.showGround()) {
      this.lastSoilQueryKey = null;
      this.scheduleSoilFetch();
    } else {
      this.soilRequestToken++;
      this.drawGroundZones();
      this.soilError.set(null);
    }
  }

  toggleRecent(): void {
    this.showRecent.set(!this.showRecent());
    this.drawMarkers();
  }

  resetFilters(): void {
    this.searchTerm.set('');
    this.minMag.set(1.0);
    this.timeWindowHours.set(24);
    this.depthFilter.set('all');
    this.showFaults.set(true);
    this.showGround.set(false);
    this.showRecent.set(true);
    this.selectedEventId.set(null);
    this.lastFaultQueryKey = null;
    this.lastSoilQueryKey = null;
    this.fetchData();
    this.scheduleFaultFetch();
    this.drawGroundZones();
    this.soilError.set(null);
  }

  toggleFiltersPanel(): void {
    this.filtersOpen.set(!this.filtersOpen());
  }

  openFiltersPanel(): void {
    this.filtersOpen.set(true);
  }

  openRightDrawer(tab: 'layers' | 'legend'): void {
    this.rightDrawerTab.set(tab);
    this.rightDrawerOpen.set(true);
  }

  closeRightDrawer(): void {
    this.rightDrawerOpen.set(false);
  }

  toggleAiDock(): void {
    this.aiDockOpen.set(!this.aiDockOpen());
  }

  closeAiDock(): void {
    this.aiDockOpen.set(false);
  }

  clearSelectedEvent(): void {
    this.selectedEventId.set(null);
  }

  onAiInput(event: Event): void {
    this.aiInput.set((event.target as HTMLInputElement).value);
  }

  askAiPreset(prompt: string): void {
    this.sendAiMessage(prompt);
  }

  sendAiMessage(prefill?: string): void {
    if (this.aiLoading()) return;

    const question = (prefill ?? this.aiInput()).trim();
    if (!question) return;

    this.aiInput.set('');
    this.aiError.set(null);
    this.pushAiMessage({ role: 'user', text: question });
    this.aiLoading.set(true);

    const bbox = this.mapLoaded
      ? ([
          this.map.getBounds().getWest(),
          this.map.getBounds().getSouth(),
          this.map.getBounds().getEast(),
          this.map.getBounds().getNorth()
        ] as [number, number, number, number])
      : undefined;

    const selected = this.selectedEq();
    const focus = selected ?? this.lastEq();
    this.aiApi.chat({
      question,
      hours: this.timeWindowHours(),
      minMagnitude: this.minMag(),
      limit: 260,
      eventId: focus?.id,
      latitude: focus?.lat,
      longitude: focus?.lng,
      bbox
    }).subscribe({
      next: (res) => {
        const bits: string[] = [];
        if (selected) bits.push('Odak: haritadan secili deprem');
        if (res.model) bits.push(`Model: ${res.model}`);
        bits.push(`Olay: ${res.eventCount}`);
        if (typeof res.nearestFaultDistanceKm === 'number') {
          bits.push(`En yakin fay: ${res.nearestFaultDistanceKm.toFixed(1)} km`);
        }
        if (res.note) bits.push(res.note);

        this.pushAiMessage({
          role: 'assistant',
          text: res.answer,
          meta: bits.join(' | ')
        });
        this.aiLoading.set(false);
      },
      error: () => {
        this.aiError.set('AI servisine ulasilamadi. Backend/Groq ayarlarini kontrol edin.');
        this.pushAiMessage({
          role: 'assistant',
          text: 'Su an AI yaniti uretilemedi. Birazdan tekrar deneyin.',
          meta: 'Hata: servis erisimi'
        });
        this.aiLoading.set(false);
      }
    });
  }

  private pushAiMessage(message: AiMessage): void {
    const next = [...this.aiMessages(), message];
    if (next.length > 28) {
      next.splice(0, next.length - 28);
    }
    this.aiMessages.set(next);
  }

  zoomIn(): void {
    if (this.mapLoaded) this.map.zoomIn({ duration: 250 });
  }

  zoomOut(): void {
    if (this.mapLoaded) this.map.zoomOut({ duration: 250 });
  }

  resetView(): void {
    if (this.mapLoaded) {
      this.map.easeTo({ center: [35.0, 39.0], zoom: 6, duration: 350 });
    }
  }

  normalizedMag(mag: number): number {
    return Math.round(mag * 10) / 10;
  }

  relativeTime(date: Date): string {
    const diffMs = Date.now() - date.getTime();
    const minutes = Math.floor(diffMs / 60000);
    if (minutes < 1) return 'simdi';
    if (minutes < 60) return `${minutes} dk once`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} sa once`;
    const days = Math.floor(hours / 24);
    return `${days} gun once`;
  }

  private tryParseCoordinates(input: string): { lat: number; lng: number } | null {
    const match = input.trim().match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
    if (!match) return null;

    const lat = Number(match[1]);
    const lng = Number(match[2]);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;

    return { lat, lng };
  }

  private normalizeText(input: string): string {
    return input
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9\s]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  private formatDate(date: Date): string {
    return new Intl.DateTimeFormat('tr-TR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    }).format(date);
  }

  private emptyFeatureCollection(): GeoJSON.FeatureCollection {
    return { type: 'FeatureCollection', features: [] };
  }
}
