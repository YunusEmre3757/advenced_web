import { Component, EventEmitter, Input, Output, computed } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface RiskTimelinePoint {
  hour: string;
  count: number;
  avgMag: number;
}

@Component({
  selector: 'app-risk-timeline',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './risk-timeline.html',
  styleUrl: './risk-timeline.css'
})
export class RiskTimeline {
  @Input() data: RiskTimelinePoint[] = [];
  @Input() activeWindow = 24;
  @Input() windows: number[] = [6, 12, 24, 72];
  @Output() windowChange = new EventEmitter<number>();

  private width = 100;
  private height = 100;

  readonly countPath = computed(() => this.buildPath('count'));
  readonly magPath = computed(() => this.buildPath('avgMag'));

  readonly maxCount = computed(() => Math.max(1, ...this.data.map(d => d.count)));
  readonly maxMag = computed(() => Math.max(1, ...this.data.map(d => d.avgMag)));
  readonly labelStep = computed(() => {
    if (this.data.length <= 12) return 2;
    if (this.data.length <= 24) return 4;
    return Math.ceil(this.data.length / 6);
  });

  private buildPath(key: 'count' | 'avgMag'): string {
    if (!this.data || this.data.length === 0) return '';
    const max = key === 'count' ? this.maxCount() : this.maxMag();
    const step = this.data.length > 1 ? this.width / (this.data.length - 1) : this.width;

    return this.data.map((point, i) => {
      const x = i * step;
      const value = key === 'count' ? point.count : point.avgMag;
      const y = this.height - ((value / max) * this.height);
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    }).join(' ');
  }

  setWindow(window: number): void {
    this.windowChange.emit(window);
  }
}
