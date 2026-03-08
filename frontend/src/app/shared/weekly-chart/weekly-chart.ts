import { Component, Input, Output, EventEmitter, computed, signal, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface TrendPoint {
  label: string;
  count: number;
}

export type TrendRange = '24s' | '3g' | '7g';
export type MagFilter = 'all' | 'm2' | 'm3' | 'm4' | 'm5';

@Component({
  selector: 'app-weekly-chart',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './weekly-chart.html',
  styleUrl: './weekly-chart.css'
})
export class WeeklyChart implements OnChanges {
  @Input() data: TrendPoint[] = [];
  @Input() activeRange: TrendRange = '7g';
  @Input() activeMag: MagFilter = 'all';
  @Output() rangeChange = new EventEmitter<TrendRange>();
  @Output() magChange = new EventEmitter<MagFilter>();

  private readonly dataSignal = signal<TrendPoint[]>([]);

  readonly ranges: { key: TrendRange; label: string }[] = [
    { key: '24s', label: '24 Saat' },
    { key: '3g', label: '3 Gün' },
    { key: '7g', label: 'Haftalık' }
  ];

  readonly magRanges: { key: MagFilter; label: string; color: string }[] = [
    { key: 'all', label: 'Tümü', color: '#60a5fa' },
    { key: 'm2', label: 'M2+', color: '#22c55e' },
    { key: 'm3', label: 'M3+', color: '#f59e0b' },
    { key: 'm4', label: 'M4+', color: '#f97316' },
    { key: 'm5', label: 'M5+', color: '#ef4444' }
  ];

  setMag(key: MagFilter): void {
    this.magChange.emit(key);
  }

  get currentLineColor(): string {
    const found = this.magRanges.find(m => m.key === this.activeMag);
    return found ? found.color : '#60a5fa';
  }

  /* SVG layout */
  readonly W = 560;
  readonly H = 200;
  private readonly PL = 42;
  private readonly PR = 15;
  private readonly PT = 18;
  private readonly PB = 28;
  readonly viewBox = `0 0 ${this.W} ${this.H}`;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['data']) this.dataSignal.set(this.data);
  }

  setRange(key: TrendRange): void {
    this.rangeChange.emit(key);
  }

  /* ---- Computed ---- */

  readonly maxVal = computed(() => {
    const d = this.dataSignal();
    if (d.length === 0) return 20;
    return Math.max(...d.map(p => p.count), 5);
  });

  readonly gridLines = computed(() => {
    const max = this.maxVal();
    const steps = 4;
    const chartH = this.H - this.PT - this.PB;
    const lines: { y: number; label: string }[] = [];
    for (let i = 0; i <= steps; i++) {
      const value = Math.round(max * (1 - i / steps));
      lines.push({ y: this.PT + chartH * (i / steps), label: value.toString() });
    }
    return lines;
  });

  readonly points = computed(() => {
    const d = this.dataSignal();
    const max = this.maxVal();
    const chartW = this.W - this.PL - this.PR;
    const chartH = this.H - this.PT - this.PB;

    return d.map((p, i) => {
      const x = this.PL + (d.length > 1 ? (i * chartW) / (d.length - 1) : chartW / 2);
      const rawY = max > 0 ? (p.count / max) * chartH : 0;
      return { x, y: this.PT + chartH - rawY, value: p.count, day: p.label };
    });
  });

  readonly linePath = computed(() => this.smooth(this.points()));

  readonly areaPath = computed(() => {
    const pts = this.points();
    if (pts.length < 2) return '';
    const base = this.H - this.PB;
    return `${this.smooth(pts)}L${pts[pts.length - 1].x},${base}L${pts[0].x},${base}Z`;
  });

  /* Catmull-Rom → Cubic Bézier */
  private smooth(pts: { x: number; y: number }[]): string {
    if (pts.length < 2) return '';
    if (pts.length === 2) return `M${pts[0].x},${pts[0].y}L${pts[1].x},${pts[1].y}`;

    let d = `M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[Math.max(0, i - 1)];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[Math.min(pts.length - 1, i + 2)];
      d += ` C${(p1.x + (p2.x - p0.x) / 6).toFixed(1)},${(p1.y + (p2.y - p0.y) / 6).toFixed(1)} ${(p2.x - (p3.x - p1.x) / 6).toFixed(1)},${(p2.y - (p3.y - p1.y) / 6).toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
    }
    return d;
  }
}
