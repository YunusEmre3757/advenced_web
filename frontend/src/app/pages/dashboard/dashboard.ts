import { AfterViewInit, Component, ElementRef, OnDestroy, OnInit, ViewChild, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import * as L from 'leaflet';
import { KpiCard } from '../../shared/kpi-card/kpi-card';
import { WeeklyChart, TrendPoint, TrendRange, MagFilter } from '../../shared/weekly-chart/weekly-chart';
import { MagDistribution, MagDistributionItem } from '../../shared/mag-distribution/mag-distribution';
import { AiInsights, AiInsightItem } from '../../shared/ai-insights/ai-insights';
import { RiskCityItem, RiskCityList } from '../../shared/risk-city-list/risk-city-list';
import { HourlyAnomaly, HourlyPoint } from '../../shared/hourly-anomaly/hourly-anomaly';
import { Earthquake, EarthquakeApi } from '../../core/earthquake-api';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    KpiCard,
    WeeklyChart,
    MagDistribution,
    AiInsights,
    RiskCityList,
    HourlyAnomaly
  ],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css'
})
export class Dashboard implements OnInit, OnDestroy, AfterViewInit {
  @ViewChild('miniMap', { static: false }) miniMapEl!: ElementRef;
  private map!: L.Map;
  private markersLayer = L.layerGroup();

  earthquakes = signal<Earthquake[]>([]);
  requestError = signal<string | null>(null);
  lastUpdated = signal<Date | null>(null);
  trendRange = signal<TrendRange>('7g');
  trendMagFilter = signal<MagFilter>('all');

  stats = signal({
    count24h: 0,
    maxMag: 0,
    avgMag: 0,
    activeWarnings: 0
  });

  nearestEq = signal<{ location: string; mag: number; distanceKm: number } | null>(null);

  constructor(private readonly earthquakeApi: EarthquakeApi) { }

  ngOnInit(): void {
    this.fetchEarthquakes();
  }

  ngAfterViewInit(): void {
    this.initMap();
  }

  ngOnDestroy(): void {
    if (this.map) this.map.remove();
  }

  riskLevel = computed<'high' | 'medium' | 'low'>(() => {
    const s = this.stats();
    if (s.maxMag >= 5.5 || s.activeWarnings >= 3) return 'high';
    if (s.maxMag >= 4.5 || s.activeWarnings >= 1) return 'medium';
    return 'low';
  });

  trendData = computed<TrendPoint[]>(() => {
    const range = this.trendRange();
    const magFilter = this.trendMagFilter();
    const now = new Date();
    const all = this.earthquakes();
    const trDays = ['Paz', 'Pzt', 'Sal', 'Car', 'Per', 'Cum', 'Cmt'];
    const result: TrendPoint[] = [];

    // Magnitude filter
    const magThreshold: Record<MagFilter, number> = {
      'all': 0, 'm2': 2, 'm3': 3, 'm4': 4, 'm5': 5
    };
    const minMag = magThreshold[magFilter];
    const filtered = minMag > 0
      ? all.filter(e => this.normalizedMag(e) >= minMag)
      : all;

    if (range === '24s') {
      // Son 24 saat, saatlik
      for (let i = 23; i >= 0; i--) {
        const start = new Date(now);
        start.setMinutes(0, 0, 0);
        start.setHours(now.getHours() - i);
        const end = new Date(start);
        end.setHours(start.getHours() + 1);
        result.push({
          label: start.getHours().toString().padStart(2, '0'),
          count: filtered.filter(eq => eq.date >= start && eq.date < end).length
        });
      }
    } else if (range === '3g') {
      // Son 3 gün, günlük
      for (let i = 2; i >= 0; i--) {
        const day = new Date(now);
        day.setHours(0, 0, 0, 0);
        day.setDate(now.getDate() - i);
        const dayEnd = new Date(day);
        dayEnd.setDate(day.getDate() + 1);
        result.push({
          label: trDays[day.getDay()],
          count: filtered.filter(eq => eq.date >= day && eq.date < dayEnd).length
        });
      }
    } else {
      // Son 7 gün, günlük
      for (let i = 6; i >= 0; i--) {
        const day = new Date(now);
        day.setHours(0, 0, 0, 0);
        day.setDate(now.getDate() - i);
        const dayEnd = new Date(day);
        dayEnd.setDate(day.getDate() + 1);
        result.push({
          label: trDays[day.getDay()],
          count: filtered.filter(eq => eq.date >= day && eq.date < dayEnd).length
        });
      }
    }
    return result;
  });

  onTrendRangeChange(range: TrendRange): void {
    this.trendRange.set(range);
  }

  onTrendMagChange(mag: MagFilter): void {
    this.trendMagFilter.set(mag);
  }

  magDistribution = computed<MagDistributionItem[]>(() => {
    const since24h = Date.now() - 24 * 60 * 60 * 1000;
    const all = this.earthquakes().filter(e => e.date.getTime() >= since24h);
    const total = all.length || 1;
    const buckets = [
      { label: 'M5.0+', count: all.filter(e => this.normalizedMag(e) >= 5).length, color: '#991b1b' },
      { label: 'M4.0-5.0', count: all.filter(e => this.normalizedMag(e) >= 4 && this.normalizedMag(e) < 5).length, color: '#ef4444' },
      { label: 'M3.0-4.0', count: all.filter(e => this.normalizedMag(e) >= 3 && this.normalizedMag(e) < 4).length, color: '#f97316' },
      { label: 'M2.0-3.0', count: all.filter(e => this.normalizedMag(e) >= 2 && this.normalizedMag(e) < 3).length, color: '#eab308' },
      { label: 'M<2.0', count: all.filter(e => this.normalizedMag(e) < 2).length, color: '#22c55e' }
    ];
    return buckets.map(b => ({ ...b, percentage: Math.round((b.count / total) * 100) }));
  });

  strongestEvents = computed(() =>
    [...this.earthquakes()].sort((a, b) => this.normalizedMag(b) - this.normalizedMag(a)).slice(0, 3)
  );

  cityRiskList = computed<RiskCityItem[]>(() => {
    const since24h = Date.now() - 24 * 60 * 60 * 1000;
    const recent = this.earthquakes().filter(e => e.date.getTime() >= since24h);
    const map = new Map<string, { count: number; maxMag: number }>();

    recent.forEach(eq => {
      const city = this.extractCity(eq.location);
      const current = map.get(city);
      const mag = this.normalizedMag(eq);
      if (!current) {
        map.set(city, { count: 1, maxMag: mag });
      } else {
        current.count += 1;
        current.maxMag = Math.max(current.maxMag, mag);
      }
    });

    return [...map.entries()]
      .map(([city, val]) => {
        const level: 'high' | 'medium' | 'low' =
          val.maxMag >= 5.0 ? 'high' : val.maxMag >= 4.0 ? 'medium' : 'low';
        return {
          city,
          count: val.count,
          maxMag: val.maxMag,
          level
        };
      })
      .sort((a, b) => (b.maxMag * 10 + b.count) - (a.maxMag * 10 + a.count))
      .slice(0, 5);
  });

  hourlySeries = computed<HourlyPoint[]>(() => {
    const now = new Date();
    const all = this.earthquakes();
    const points: HourlyPoint[] = [];

    for (let i = 11; i >= 0; i--) {
      const start = new Date(now);
      start.setMinutes(0, 0, 0);
      start.setHours(now.getHours() - i);
      const end = new Date(start);
      end.setHours(start.getHours() + 1);
      points.push({
        hour: start.getHours().toString().padStart(2, '0'),
        count: all.filter(eq => eq.date >= start && eq.date < end).length
      });
    }
    return points;
  });

  anomaly = computed(() => {
    const series = this.hourlySeries();
    if (series.length === 0) {
      return {
        latest: 0,
        baseline: 0,
        level: 'low' as const,
        message: 'Anomali analizi icin yeterli veri yok.'
      };
    }

    const latest = series[series.length - 1].count;
    const previous = series.slice(0, series.length - 1).map(s => s.count);
    const baseline = previous.length > 0
      ? previous.reduce((a, b) => a + b, 0) / previous.length
      : 0;

    if (latest >= 5 && latest > baseline * 1.8) {
      return {
        latest,
        baseline,
        level: 'high' as const,
        message: 'Son 1 saatte belirgin aktivite artisi var. Yerel akis yakindan izlenmeli.'
      };
    }
    if (latest > baseline * 1.2) {
      return {
        latest,
        baseline,
        level: 'medium' as const,
        message: 'Aktivite baz degerin uzerinde. Kisa sureli artislara karsi takip onerilir.'
      };
    }
    return {
      latest,
      baseline,
      level: 'low' as const,
      message: 'Son 1 saat aktivitesi normal aralikta.'
    };
  });

  aiInsights = computed<AiInsightItem[]>(() => {
    const top = this.strongestEvents();
    const cityTop = this.cityRiskList();
    const anomaly = this.anomaly();
    const list: AiInsightItem[] = [];

    list.push({
      title: 'Anlik Durum',
      severity: this.riskLevel(),
      text: `Son 24 saatte ${this.stats().count24h} olay izlendi. Risk seviyesi: ${this.riskLabel(this.riskLevel())}.`
    });

    if (top.length > 0) {
      list.push({
        title: 'En Guclu Olay',
        severity: this.normalizedMag(top[0]) >= 5 ? 'high' : 'medium',
        text: `${top[0].location} bolgesinde M${this.normalizedMag(top[0]).toFixed(1)} olayi kaydedildi.`
      });
    }

    if (cityTop.length > 0) {
      list.push({
        title: 'Il Odak Noktasi',
        severity: cityTop[0].level,
        text: `${cityTop[0].city} son 24 saatte ${cityTop[0].count} olay ile en hareketli bolge.`
      });
    }

    list.push({
      title: 'Anomali Uyarisi',
      severity: anomaly.level,
      text: anomaly.message
    });

    return list;
  });

  aiHeadline = computed(() => {
    const s = this.stats();
    const anomaly = this.anomaly();
    return `AI Copilot: Son 24 saatte ${s.count24h} olay, en yuksek M${s.maxMag.toFixed(1)}. ` +
      `Anomali seviyesi: ${anomaly.level === 'high' ? 'Yuksek' : anomaly.level === 'medium' ? 'Orta' : 'Normal'}.`;
  });

  aiActions = computed(() => {
    const actions: string[] = [];
    const s = this.stats();
    const anomaly = this.anomaly();
    const topCity = this.cityRiskList()[0];

    if (s.maxMag >= 5.0) actions.push('M5+ olaylar icin saha ekibi ve bildirim zincirini aktif tut.');
    if (anomaly.level === 'high') actions.push('Son 1 saatte artis var, 30 dakikalik sik izleme moduna gec.');
    if (topCity) actions.push(`${topCity.city} icin yerel iletisim ve teyit akislarini hizlandir.`);
    if (actions.length === 0) actions.push('Sistem stabil. Rutin 60 dakikalik izleme dongusune devam et.');

    return actions.slice(0, 3);
  });

  fetchEarthquakes(): void {
    this.earthquakeApi.getRecent(168, 1, 500).subscribe({
      next: (data) => {
        this.earthquakes.set(data);
        this.updateStats(data);
        this.updateNearest(data);
        this.updateMapMarkers(data);
        this.lastUpdated.set(new Date());
        this.requestError.set(null);
      },
      error: () => {
        this.earthquakes.set([]);
        this.stats.set({ count24h: 0, maxMag: 0, avgMag: 0, activeWarnings: 0 });
        this.nearestEq.set(null);
        this.requestError.set('Veri su anda alinamiyor. Kaynak erisimi kontrol edin.');
      }
    });
  }

  private updateStats(data: Earthquake[]): void {
    if (data.length === 0) return;
    const since24h = Date.now() - 24 * 60 * 60 * 1000;
    const in24h = data.filter(e => e.date.getTime() >= since24h);
    const source = in24h.length > 0 ? in24h : data;
    const mags = source.map(e => this.normalizedMag(e));

    this.stats.set({
      count24h: in24h.length,
      maxMag: parseFloat(Math.max(...mags).toFixed(1)),
      avgMag: parseFloat((mags.reduce((a, b) => a + b, 0) / mags.length).toFixed(1)),
      activeWarnings: source.filter(e => this.normalizedMag(e) >= 5).length
    });
  }

  private updateNearest(data: Earthquake[]): void {
    if (data.length === 0) return;
    const nearest = data.reduce((prev, curr) =>
      curr.distanceKm < prev.distanceKm ? curr : prev
    );
    this.nearestEq.set({
      location: nearest.location,
      mag: this.normalizedMag(nearest),
      distanceKm: nearest.distanceKm
    });
  }

  private initMap(): void {
    const bounds: L.LatLngBoundsLiteral = [[35.0, 25.0], [43.0, 45.0]];
    this.map = L.map(this.miniMapEl.nativeElement, {
      center: [39.0, 35.0],
      zoom: 6,
      minZoom: 5,
      maxZoom: 10,
      attributionControl: false,
      scrollWheelZoom: false,
      maxBounds: bounds,
      maxBoundsViscosity: 1.0
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}{r}.png', { maxZoom: 18 }).addTo(this.map);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png', { maxZoom: 18, pane: 'overlayPane' }).addTo(this.map);

    this.markersLayer.addTo(this.map);
    if (this.earthquakes().length > 0) this.updateMapMarkers(this.earthquakes());
  }

  private updateMapMarkers(data: Earthquake[]): void {
    if (!this.map) return;
    this.markersLayer.clearLayers();

    data.slice(0, 180).forEach(eq => {
      const mag = this.normalizedMag(eq);
      const color = mag >= 5 ? '#991b1b' : mag >= 4 ? '#ef4444' : mag >= 3 ? '#f97316' : mag >= 2 ? '#eab308' : '#22c55e';
      const radius = mag >= 6 ? 12 : mag >= 5 ? 10 : mag >= 4 ? 8 : mag >= 3 ? 6 : 4;
      const marker = L.circleMarker([eq.lat, eq.lng], {
        radius,
        fillColor: color,
        color: 'rgba(0,0,0,0.28)',
        weight: 1,
        fillOpacity: 0.9
      });

      marker.bindPopup(
        `<div style="font-size:13px;font-weight:600;color:#1a1a2e">${eq.location}</div>` +
        `<div style="font-size:12px;color:#555">M${mag.toFixed(1)} | ${eq.depth.toFixed(0)} km derinlik</div>`
      );

      if (mag >= 3) {
        marker.bindTooltip(mag.toFixed(1), {
          permanent: true,
          direction: 'top',
          className: 'map-mag-label',
          offset: [0, -radius]
        });
      }
      this.markersLayer.addLayer(marker);
    });
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

  riskLabel(level: 'high' | 'medium' | 'low'): string {
    if (level === 'high') return 'Yuksek';
    if (level === 'medium') return 'Orta';
    return 'Dusuk';
  }

  normalizedMag(eq: Earthquake): number {
    return Math.round(eq.mag * 10) / 10;
  }

  private extractCity(location: string): string {
    const candidates = [
      'istanbul', 'ankara', 'izmir', 'bursa', 'antalya', 'konya', 'adana', 'mugla', 'hatay',
      'kahramanmaras', 'malatya', 'elazig', 'erzincan', 'erzurum', 'kocaeli', 'sakarya',
      'balikesir', 'canakkale', 'tekirdag', 'aydin', 'denizli', 'afyonkarahisar', 'usak', 'manisa',
      'bingol', 'van', 'diyarbakir', 'gaziantep', 'mardin', 'sivas', 'ordu', 'samsun', 'trabzon'
    ];
    const n = this.normalizeText(location);
    for (const city of candidates) {
      if (n.includes(city)) return this.toTitle(city);
    }
    const raw = location.split(/[-,]/)[0]?.trim() ?? 'Bilinmeyen';
    return this.toTitle(this.normalizeText(raw));
  }

  private normalizeText(input: string): string {
    return input.toLowerCase()
      .replace(/ı/g, 'i').replace(/ğ/g, 'g').replace(/ü/g, 'u')
      .replace(/ş/g, 's').replace(/ö/g, 'o').replace(/ç/g, 'c')
      .replace(/[^a-z0-9\s]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  private toTitle(input: string): string {
    return input.split(' ').filter(Boolean)
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  }
}
