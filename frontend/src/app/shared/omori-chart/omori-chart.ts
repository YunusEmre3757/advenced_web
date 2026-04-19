import { AfterViewInit, Component, ElementRef, Input, OnChanges, SimpleChanges, ViewChild } from '@angular/core';
import { Earthquake } from '../../core/earthquake-api';

@Component({
  selector: 'app-omori-chart',
  standalone: true,
  imports: [],
  template: `
    <div class="omori-wrap">
      <div class="omori-head">
        <span class="label">Omori artci azalma egrisi</span>
        <small>K={{ k.toFixed(2) }} &middot; c={{ c.toFixed(2) }} &middot; p={{ p.toFixed(2) }}</small>
      </div>
      <svg #svgEl viewBox="0 0 320 120" preserveAspectRatio="none" class="omori-svg"></svg>
      <small class="omori-note">Nokta: olcum &middot; Cizgi: Omori uyumu n(t) = K / (t+c)^p</small>
    </div>
  `,
  styles: [`
    :host { display: block; }
    .omori-wrap { padding: 0.7rem 0.85rem; border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; background: rgba(15,23,42,0.74); }
    .omori-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.35rem; }
    .label { color: #f2f7ff; font-size: 0.82rem; font-weight: 800; }
    small { color: #9fb2ce; font-size: 0.72rem; }
    .omori-svg { width: 100%; height: 130px; display: block; }
    .omori-note { display: block; margin-top: 0.3rem; }
  `]
})
export class OmoriChart implements AfterViewInit, OnChanges {
  @Input() mainshockTime!: Date;
  @Input() mainshockMagnitude = 4;
  @Input() aftershocks: Earthquake[] = [];

  @ViewChild('svgEl', { static: false }) svgEl?: ElementRef<SVGSVGElement>;

  k = 0;
  c = 0.5;
  p = 1.0;

  ngAfterViewInit(): void {
    this.render();
  }

  ngOnChanges(_changes: SimpleChanges): void {
    if (this.svgEl) this.render();
  }

  private render(): void {
    if (!this.svgEl || !this.mainshockTime) {
      return;
    }

    const mainMs = this.mainshockTime.getTime();
    const times = this.aftershocks
      .map(a => (a.date.getTime() - mainMs) / 3600_000)
      .filter(h => h > 0.02 && h < 72 * 4)
      .sort((a, b) => a - b);

    const bins = 14;
    const maxT = Math.max(...times, 72);
    const binSize = maxT / bins;
    const counts = new Array(bins).fill(0);
    for (const t of times) {
      const idx = Math.min(bins - 1, Math.floor(t / binSize));
      counts[idx] += 1;
    }
    const ratePoints = counts.map((cnt, i) => ({
      t: (i + 0.5) * binSize,
      rate: cnt / binSize,
    })).filter(p => p.rate > 0);

    const totalWindow = maxT;
    this.k = Math.max(times.length, this.modelK(this.mainshockMagnitude));
    this.c = 0.5;
    this.p = 1.0;
    const pred = (t: number) => {
      const integral = this.k * (this.p === 1
        ? Math.log((t + this.c) / this.c)
        : (Math.pow(t + this.c, 1 - this.p) - Math.pow(this.c, 1 - this.p)) / (1 - this.p));
      return integral;
    };
    const scale = times.length / pred(totalWindow);
    this.k = scale;

    const omori = (t: number) => this.k / Math.pow(t + this.c, this.p);

    const W = 320, H = 120, pad = 18;
    const maxRate = Math.max(0.1, ...ratePoints.map(p => p.rate), omori(Math.max(0.01, binSize / 2)));
    const xScale = (t: number) => pad + (t / maxT) * (W - pad - 5);
    const yScale = (r: number) => H - pad + 4 - (r / maxRate) * (H - pad - 10);

    let path = '';
    const steps = 80;
    for (let i = 0; i <= steps; i++) {
      const t = (i / steps) * maxT;
      const y = yScale(omori(Math.max(0.05, t)));
      path += (i === 0 ? 'M' : 'L') + xScale(t).toFixed(1) + ' ' + y.toFixed(1) + ' ';
    }

    const dots = ratePoints.map(p =>
      `<circle cx="${xScale(p.t).toFixed(1)}" cy="${yScale(p.rate).toFixed(1)}" r="2.5" fill="#7dd3fc"/>`
    ).join('');

    const xAxis = `<line x1="${pad}" y1="${H - pad + 4}" x2="${W - 5}" y2="${H - pad + 4}" stroke="rgba(255,255,255,0.18)" stroke-width="0.6"/>`;
    const yAxis = `<line x1="${pad}" y1="6" x2="${pad}" y2="${H - pad + 4}" stroke="rgba(255,255,255,0.18)" stroke-width="0.6"/>`;
    const label = `<text x="${W - 5}" y="${H - 4}" text-anchor="end" fill="#8fa5c5" font-size="9">saat sonra</text>`;
    const yLabel = `<text x="4" y="12" fill="#8fa5c5" font-size="9">oran</text>`;

    const emptyLabel = times.length === 0
      ? '<text x="160" y="61" text-anchor="middle" fill="#8fa5c5" font-size="10">Olculen artci yok - turuncu cizgi teorik azalma</text>'
      : '';

    this.svgEl.nativeElement.innerHTML =
      xAxis + yAxis + label + yLabel +
      `<path d="${path}" stroke="#f97316" stroke-width="1.5" fill="none"/>` +
      dots + emptyLabel;
  }

  private modelK(magnitude: number): number {
    if (magnitude >= 6) return 9;
    if (magnitude >= 5) return 5;
    if (magnitude >= 4) return 2.2;
    if (magnitude >= 3) return 1.2;
    return 0.6;
  }
}
